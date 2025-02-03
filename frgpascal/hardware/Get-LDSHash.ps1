param(
    [Parameter(Mandatory=$true)]
    [string]$VID,
    
    [Parameter(Mandatory=$true)]
    [string]$ProdID
)

# Enumerate all PnP devices and filter by InstanceId containing the target VID and ProdID.
$devices = Get-PnpDevice | Where-Object { $_.InstanceId -match "VID_$VID" -and $_.InstanceId -match "PID_$ProdID" }

foreach ($device in $devices) {
    $instanceId = $device.InstanceId
    
    # Retrieve the Reported Device IDs Hash property.
    $ldsProp = Get-PnpDeviceProperty -InstanceId $instanceId -KeyName 'DEVPKEY_Device_ReportedDeviceIdsHash' -ErrorAction SilentlyContinue
    if ($ldsProp -and $ldsProp.Data) {
        # Retrieve the friendly name property (which typically contains the COM port in parentheses)
        $friendlyProp = Get-PnpDeviceProperty -InstanceId $instanceId -KeyName 'DEVPKEY_Device_FriendlyName' -ErrorAction SilentlyContinue
        if ($friendlyProp -and $friendlyProp.Data) {
            if ($friendlyProp.Data -match "\((COM\d+)\)") {
                $comPort = $Matches[1]
            } else {
                $comPort = "N/A"
            }
        } else {
            $comPort = "N/A"
        }
        # Output both the COM port and the LDS hash.
        Write-Output "COM Port: $comPort | LDS Hash: $($ldsProp.Data)"
    }
}
