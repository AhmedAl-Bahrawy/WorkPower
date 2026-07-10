"""Windows balloon notifications."""

import subprocess


def notify(title, message):
    safe_title = title.replace("'", "''")
    safe_msg = message.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;"
        f"$n.ShowBalloonTip(4000,'{safe_title}','{safe_msg}',"
        "[System.Windows.Forms.ToolTipIcon]::None);"
        "Start-Sleep -s 5;$n.Dispose()"
    )
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script]
        )
    except Exception:
        pass
