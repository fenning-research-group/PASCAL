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
    $prop = Get-PnpDeviceProperty -InstanceId $instanceId -KeyName 'DEVPKEY_Device_ReportedDeviceIdsHash' -ErrorAction SilentlyContinue
    if ($prop -and $prop.Data) {
        # Write out the LDS hash. Each hash will be on its own line.
        Write-Output $prop.Data
        # Flush the output immediately
        [Console]::Out.Flush()
    }
}
