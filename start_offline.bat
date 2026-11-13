@echo off
cd /d "%~dp0"
echo Starting a second console on port 8766 for the offline demo. The first console can keep running a scan.
python launch.py 8766 || py launch.py 8766
pause
