# PyInstaller hook for segments package
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('segments')
hiddenimports = collect_submodules('segments')
