' Túnel local para a extensão MNEME no Windows.
' O WScript não abre console. Se o SSH cair, a conexão é tentada novamente.
Option Explicit

Dim shell, ssh, argumentos
Set shell = CreateObject("WScript.Shell")
ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
argumentos = " -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -L 127.0.0.1:8787:127.0.0.1:8787 mneme-a1"

Do
  shell.Run Chr(34) & ssh & Chr(34) & argumentos, 0, True
  WScript.Sleep 5000
Loop
