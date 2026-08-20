Option Explicit

Dim shell, command, index, value, exitCode

If WScript.Arguments.Count < 1 Then
    WScript.Quit 64
End If

Set shell = CreateObject("WScript.Shell")
command = "powershell.exe -NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " & QuoteArgument(WScript.Arguments(0))

For index = 1 To WScript.Arguments.Count - 1
    value = CStr(WScript.Arguments(index))
    If InStr(value, Chr(34)) > 0 Then
        WScript.Quit 65
    End If
    command = command & " " & QuoteArgument(value)
Next

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

Function QuoteArgument(value)
    QuoteArgument = Chr(34) & CStr(value) & Chr(34)
End Function
