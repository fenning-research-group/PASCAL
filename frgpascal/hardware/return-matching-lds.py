import subprocess
import sys


def find_matching_device(vid=None, pid=None, lds_hash=None):
    # Set your target values
    # target_vid = "1EAF"
    # target_prodid = "0004"
    # target_hash = "2875070560"  # The hash you're looking for (in decimal string format)

    # Path to the PowerShell script (assumed to be in the same directory)
    ps_script = "Get-LDSHash.ps1"

    # Build the command. The -NoProfile and -ExecutionPolicy Bypass options help avoid policy issues.
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
        # Start the PowerShell process with stdout piped
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

        found = False
        # Read output line by line as it is produced.
        while True:
            line = process.stdout.readline()
            # If no more output and process has ended, break out of the loop.
            if line == "" and process.poll() is not None:
                break
            if line:
                line = line.strip()
                if line:
                    print(f"Received LDS hash: {line}")
                    # Check if the line matches our target hash.
                    if line == lds_hash:
                        print("Match found!")
                        found = True
                        # Terminate the PowerShell process early.
                        process.terminate()
                        break
        # Clean up
        process.stdout.close()
        process.wait()

        if found:
            print("Device with matching LDS hash found.")
            sys.exit(0)
        else:
            print("No device with the matching LDS hash was found.")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print("Error calling PowerShell script:")
        print(e.output)
        sys.exit(1)
