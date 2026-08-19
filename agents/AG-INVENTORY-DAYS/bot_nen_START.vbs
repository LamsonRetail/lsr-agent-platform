' ============================================================
'  Chay bot AN (khong hien cua so). Bam doi chuot vao file nay.
'  Bot chay tiep ca khi dong het cua so — chi dung khi tat may
'  hoac bam bot_nen_STOP.bat.
'  Nhat ky ghi vao bot_log.txt cung thu muc.
' ============================================================
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName) & "\"

' Da chay roi thi khong chay them cai thu hai.
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set ps = wmi.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='python.exe'")
For Each p In ps
  If Not IsNull(p.CommandLine) Then
    If InStr(p.CommandLine, "bot_poll.py") > 0 Then
      MsgBox "Bot dang chay roi." & vbCrLf & vbCrLf & _
             "Muon dung thi bam bot_nen_STOP.bat.", 64, "PLANNING' ASSISTANT"
      WScript.Quit
    End If
  End If
Next

sh.Run """" & root & "_bot_loop.bat""", 0, False
MsgBox "Bot da chay nen." & vbCrLf & vbCrLf & _
       "Thu gui cau hoi vao nhom Lark." & vbCrLf & _
       "Nhat ky: bot_log.txt" & vbCrLf & _
       "Dung bot: bam bot_nen_STOP.bat", 64, "PLANNING' ASSISTANT"
