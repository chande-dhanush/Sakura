# PyInstaller hook for misaki package
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('misaki')
hiddenimports = collect_submodules('misaki')
