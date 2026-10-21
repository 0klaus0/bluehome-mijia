package app.bluehome.companion;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
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
        if (validHost(savedHost)) { host = savedHost; showWeb(); }
        else showConnect();
    }

    private boolean validHost(String value) {
        if (!value.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) return false;
        try {
            InetAddress address = InetAddress.getByName(value);
            return address.isSiteLocalAddress() && !address.isLoopbackAddress();
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
        hint.setText("输入飞牛 NAS 的局域网 IP。首次连接时，在 NAS 的栖居容器日志中查看八位配对码。手机与 NAS 需连接同一局域网。");
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
            if (!validHost(value)) { error.setText("请输入 NAS 的局域网 IPv4 地址"); return; }
            host = value;
            getPreferences(0).edit().putString("host",host).apply();
            showWeb();
        });
        setContentView(root);
    }

    private void showWeb() {
        root = container();
        LinearLayout bar = new LinearLayout(this); bar.setGravity(Gravity.CENTER_VERTICAL);
        Button back = new Button(this); back.setText("更换 NAS");
        back.setOnClickListener(v -> { if (web != null) { web.destroy(); web = null; } showConnect(); });
        bar.addView(back);
        TextView address = new TextView(this); address.setText("  " + host + ":4174");
        address.setTextColor(Color.rgb(100,124,160));bar.addView(address);
        root.addView(bar);
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
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("http".equals(uri.getScheme()) && host.equals(uri.getHost()) && uri.getPort() == 4174) return false;
                if ("https".equals(uri.getScheme())) startActivity(new Intent(Intent.ACTION_VIEW,uri));
                return true;
            }
        });
        root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        web.loadUrl("http://"+host+":4174/app/");
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
