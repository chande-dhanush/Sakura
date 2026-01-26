# PyInstaller hook for csvw package
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('csvw')
hiddenimports = collect_submodules('csvw')
