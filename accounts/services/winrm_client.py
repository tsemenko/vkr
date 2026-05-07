from __future__ import annotations


class WinRMClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        transport: str = "ntlm",
    ):
        # 5985 обычно используется для HTTP, 5986 — для HTTPS.
        scheme = "https" if int(port) == 5986 or transport.lower() in {"ssl", "https"} else "http"
        self.endpoint = f"{scheme}://{host}:{port}/wsman"
        self.username = username
        self.password = password
        self.transport = transport

    def _run_ps_via_stdin(self, script: str):
        import winrm

        p = winrm.Protocol(endpoint=self.endpoint, transport=self.transport, username=self.username, password=self.password)
        shell_id = None
        command_id = None
        try:
            shell_id = p.open_shell()
            command_id = p.run_command(
                shell_id,
                "powershell",
                [
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "[Console]::InputEncoding=[Text.Encoding]::Unicode; $s=[Console]::In.ReadToEnd(); Invoke-Expression $s",
                ],
            )
            # Скрипт передается через stdin, чтобы не упереться в ограничение длины командной строки Windows.
            data = (script.rstrip() + "\n").encode("utf-16le", errors="replace")
            if hasattr(p, "send_command_input"):
                p.send_command_input(shell_id, command_id, data, end=True)
            else:
                raise RuntimeError("Установленная версия pywinrm не поддерживает передачу PowerShell через stdin")
            std_out, std_err, status_code = p.get_command_output(shell_id, command_id)
            out = (std_out or b"").decode("utf-8", errors="replace")
            err = (std_err or b"").decode("utf-8", errors="replace")
            return status_code, out, err
        finally:
            try:
                if shell_id and command_id:
                    p.cleanup_command(shell_id, command_id)
            except Exception:
                pass
            try:
                if shell_id:
                    p.close_shell(shell_id)
            except Exception:
                pass

    def run_ps(self, script: str):
        try:
            try:
                return self._run_ps_via_stdin(script)
            except Exception:
                import winrm

                session = winrm.Session(self.endpoint, auth=(self.username, self.password), transport=self.transport)
                result = session.run_ps(script)
                out = (result.std_out or b"").decode("utf-8", errors="replace")
                err = (result.std_err or b"").decode("utf-8", errors="replace")
                return result.status_code, out, err
        except Exception as exc:
            return 1, "", f"Ошибка WinRM: {exc}"
