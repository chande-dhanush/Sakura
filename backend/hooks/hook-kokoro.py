# PyInstaller hook for kokoro package
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('kokoro')
hiddenimports = collect_submodules('kokoro')
