# PyInstaller hook for espeakng_loader
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect espeak-ng-data directory
datas = collect_data_files('espeakng_loader', include_py_files=True)
hiddenimports = collect_submodules('espeakng_loader')
