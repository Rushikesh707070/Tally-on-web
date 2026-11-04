@echo off
echo === OneDeskBiz EXE builder (Windows par ek baar chalao) ===
pip install pyinstaller requests fastapi uvicorn
pyinstaller --noconfirm --onefile --windowed --name OneDeskBiz-Connector connector_gui.py
pyinstaller --noconfirm --onefile --windowed --name OneDeskBiz-App --add-data "web.html;." --collect-submodules uvicorn --hidden-import server server_gui.py
echo.
echo Done! EXE files yaha hain: dist\OneDeskBiz-Connector.exe  aur  dist\OneDeskBiz-App.exe
pause
