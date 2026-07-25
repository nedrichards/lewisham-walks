python = import('python')
py_install = python.find_installation('python3')

test(
  'unit-tests',
  py_install,
  args: ['-m', 'unittest', 'discover', '-s', meson.current_source_dir()],
  env: [
    'GSETTINGS_BACKEND=memory',
    'PYTHONPATH=' + meson.project_source_root() / 'src',
  ],
)
