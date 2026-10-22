package app.bluehome.companion;

import android.app.Activity;
import android.content.Intent;
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

public final class MainActivity extends Activity {
    private LinearLayout root;
    private WebView web;
    private String host;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(245,248,253));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        String savedHost = getPreferences(0).getString("host", "");
        if (validHost(savedHost)) { host = savedHost; showWeb(false); }
        else showConnect();
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
        hint.setText("输入飞牛 NAS 的局域网 IP，或已连接 Tailscale 的 NAS 100.x 地址。首次连接时，请在栖居容器日志中查看八位配对码。");
        hint.setTextSize(13); hint.setTextColor(Color.rgb(113,134,163)); hint.setPadding(0,16,0,16);
        root.addView(hint);
        EditText input = new EditText(this);
        input.setSingleLine(true); input.setHint("例如 192.168.1.10");
        input.setText(getPreferences(0).getString("host",""));
        root.addView(input);
        Button connect = new Button(this); connect.setText("连接并配对"); root.addView(connect);
        TextView error = new TextView(this); error.setTextColor(Color.rgb(189,69,69));
        root.addView(error);
        connect.setOnClickListener(v -> {
            String value = input.getText().toString().trim();
            if (!validHost(value)) { error.setText("请输入 NAS 的局域网或 Tailscale IPv4 地址"); return; }
            host = value;
            getPreferences(0).edit().putString("host",host).apply();
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
        TextView address = new TextView(this); address.setText("  " + host + ":4174");
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
                        + "）。请先用手机浏览器打开 http://" + host + ":4174/pair，检查地址与网络；外网访问请先连接 Tailscale。");
                connectionError.setVisibility(View.VISIBLE);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("http".equals(uri.getScheme()) && host.equals(uri.getHost()) && uri.getPort() == 4174) return false;
                if ("https".equals(uri.getScheme())) startActivity(new Intent(Intent.ACTION_VIEW,uri));
                return true;
            }
        });
        root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        web.loadUrl("http://"+host+":4174/"+(firstConnect?"pair":"app/"));
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
