# PyInstaller hook for phonemizer package
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('phonemizer')
hiddenimports = collect_submodules('phonemizer')
