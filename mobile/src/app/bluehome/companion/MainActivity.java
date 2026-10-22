package app.bluehome.companion;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.net.InetAddress;
import java.net.URI;

public final class MainActivity extends Activity {
    private LinearLayout root;
    private WebView web;
    private String endpoint;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(245,248,253));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        String savedEndpoint = getPreferences(0).getString("endpoint", "");
        if (savedEndpoint.isEmpty()) savedEndpoint = getPreferences(0).getString("host", "");
        if (validEndpoint(savedEndpoint)) { endpoint = normalizeEndpoint(savedEndpoint); showWeb(false); }
        else showConnect();
    }

    private String normalizeEndpoint(String value) {
        return value.startsWith("https://") ? value.replaceAll("/+$", "") : "http://" + value + ":4174";
    }

    private boolean validEndpoint(String value) {
        if (validHost(value)) return true;
        try {
            URI uri = new URI(value);
            String name = uri.getHost();
            return "https".equals(uri.getScheme()) && name != null
                    && name.matches("(?i)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}")
                    && uri.getPort() == -1 && uri.getUserInfo() == null
                    && (uri.getPath() == null || uri.getPath().isEmpty() || "/".equals(uri.getPath()))
                    && uri.getQuery() == null && uri.getFragment() == null;
        } catch (Exception ignored) { return false; }
    }

    private boolean validHost(String value) {
        if (!value.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) return false;
        try {
            InetAddress address = InetAddress.getByName(value);
            byte[] octets = address.getAddress();
            boolean tailscale = octets.length == 4 && (octets[0] & 0xff) == 100
                    && ((octets[1] & 0xff) >= 64) && ((octets[1] & 0xff) <= 127);
            return (address.isSiteLocalAddress() && !address.isLoopbackAddress()) || tailscale;
        } catch (Exception ignored) { return false; }
    }

    private LinearLayout container() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(24, 30, 24, 20);
        box.setBackgroundColor(Color.rgb(246,248,252));
        return box;
    }

    private void showConnect() {
        root = container();
        TextView title = new TextView(this);
        title.setText("栖居 · 连接家庭"); title.setTextSize(23); title.setTextColor(Color.rgb(37,56,87));
        root.addView(title);
        TextView hint = new TextView(this);
        hint.setText("输入飞牛 NAS 的局域网 IP，或栖居专用的 HTTPS 域名。首次连接时，请在栖居容器日志中查看八位配对码。");
        hint.setTextSize(13); hint.setTextColor(Color.rgb(113,134,163)); hint.setPadding(0,16,0,16);
        root.addView(hint);
        EditText input = new EditText(this);
        input.setSingleLine(true); input.setHint("192.168.3.188 或 https://home.example.com");
        input.setText(getPreferences(0).getString("endpoint", getPreferences(0).getString("host","")));
        root.addView(input);
        Button connect = new Button(this); connect.setText("连接并配对"); root.addView(connect);
        TextView error = new TextView(this); error.setTextColor(Color.rgb(189,69,69));
        root.addView(error);
        connect.setOnClickListener(v -> {
            String value = input.getText().toString().trim();
            if (!validEndpoint(value)) { error.setText("请输入 NAS 局域网 IP 或完整 HTTPS 域名"); return; }
            endpoint = normalizeEndpoint(value);
            getPreferences(0).edit().putString("endpoint",endpoint).apply();
            showWeb(true);
        });
        setContentView(root);
    }

    private void showWeb(boolean firstConnect) {
        root = container();
        LinearLayout bar = new LinearLayout(this); bar.setGravity(Gravity.CENTER_VERTICAL);
        Button back = new Button(this); back.setText("更换 NAS");
        back.setOnClickListener(v -> { if (web != null) { web.destroy(); web = null; } showConnect(); });
        bar.addView(back);
        TextView address = new TextView(this); address.setText("  " + endpoint);
        address.setTextColor(Color.rgb(100,124,160));bar.addView(address);
        root.addView(bar);
        TextView connectionError = new TextView(this);
        connectionError.setTextColor(Color.rgb(171,59,59));
        connectionError.setTextSize(13);
        connectionError.setPadding(4,8,4,8);
        connectionError.setVisibility(View.GONE);
        root.addView(connectionError);
        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, Bitmap favicon) {
                connectionError.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (!request.isForMainFrame()) return;
                connectionError.setText("无法连接 NAS：" + error.getDescription() + "（" + error.getErrorCode()
                        + "）。请先用手机浏览器打开 " + endpoint + "/pair，检查地址与网络。");
                connectionError.setVisibility(View.VISIBLE);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (uri.toString().startsWith(endpoint + "/")) return false;
                String name = uri.getHost();
                if ("https".equals(uri.getScheme()) && name != null
                        && (name.equals("cloudflareaccess.com") || name.endsWith(".cloudflareaccess.com"))) return false;
                return true;
            }
        });
        root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        web.loadUrl(endpoint + "/" + (firstConnect ? "pair" : "app/"));
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
