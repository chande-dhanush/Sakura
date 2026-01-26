# PyInstaller hook for language_tags package
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('language_tags')
hiddenimports = collect_submodules('language_tags')
