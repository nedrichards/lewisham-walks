test(
  'unit-tests',
  py_install,
  args: ['-m', 'unittest', 'discover', '-s', meson.current_source_dir()],
  env: [
    'GSETTINGS_BACKEND=memory',
    'PYTHONPATH=' + meson.project_source_root() / 'src',
  ],
)
