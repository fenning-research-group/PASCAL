import subprocess
import sys


def get_lds(vid, pid):
    if len(sys.argv) < 3:
        print("Usage: python call_ldshash.py <VID> <ProdID>")
        sys.exit(1)

    vid = sys.argv[1]
    pid = sys.argv[2]

    # Path to the PowerShell script (assumed to be in the same directory)
    ps_script = "Get-LDSHash.ps1"

    # Build the command.
    # The -NoProfile and -ExecutionPolicy Bypass options help avoid policy issues.
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ps_script,
        "-VID",
        vid,
        "-ProdID",
        pid,
    ]

    try:
        # Run the PowerShell script and capture its output as text.
        output = subprocess.check_output(command, universal_newlines=True)
        output = output.strip()
        if output:
            print("LDS Hash(es) for device(s) with VID {} and PID {}:".format(vid, pid))
            print(output)
        else:
            print(
                "No devices with VID {} and PID {} that expose an LDS hash were found.".format(
                    vid, pid
                )
            )
    except subprocess.CalledProcessError as e:
        print("Error calling PowerShell script:")
        print(e.output)
