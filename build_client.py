import os
import subprocess
import sys

def build_exe():
    print("Building client application with PyInstaller...")
    
    # Path setup
    entry_point = os.path.join("client", "main.py")
    
    # Basic command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        "--name=ourvideo",
        entry_point
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print("\nBuild successful! The executable is located in the 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("\nError: PyInstaller not found. Please install dependencies using: pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
