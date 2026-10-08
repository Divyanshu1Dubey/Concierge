$cs = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges
$cs.AutomaticManagedPagefile = $false
$pf = Get-WmiObject Win32_PageFileSetting -Filter "Name='C:\\pagefile.sys'"
if ($pf) {
    $pf.InitialSize = 32768
    $pf.MaximumSize = 65536
    $pf.Put() | Out-Null
} else {
    Set-WmiInstance -Class Win32_PageFileSetting -Arguments @{Name='C:\pagefile.sys'; InitialSize=32768; MaximumSize=65536} | Out-Null
}
Write-Host "Pagefile updated. A restart is required for changes to take effect."
