pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'lewisham_walks'
python = import('python')
py_install = python.find_installation('python3')

conf = configuration_data()
conf.set('PYTHON', py_install.full_path())
conf.set('VERSION', meson.project_version())
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'lewishamwalks.in',
  output: 'com.nedrichards.lewishamwalks',
  configuration: conf,
  install: true,
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)

gnome.compile_resources(
  'lewisham-walks',
  'lewisham-walks.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

install_data(
  [
    'lewisham_walks/__init__.py',
    'lewisham_walks/discovery.py',
    'lewisham_walks/export.py',
    'lewisham_walks/map_geometry.py',
    'lewisham_walks/map_style.py',
    'lewisham_walks/main.py',
    'lewisham_walks/models.py',
    'lewisham_walks/planner.py',
    'lewisham_walks/store.py',
  ],
  install_dir: moduledir,
)

install_data(
  [
    'lewisham_walks/providers/__init__.py',
    'lewisham_walks/providers/amenities.py',
    'lewisham_walks/providers/geocoding.py',
    'lewisham_walks/providers/location.py',
    'lewisham_walks/providers/routing.py',
  ],
  install_dir: moduledir / 'providers',
)

install_data(
  [
    'lewisham_walks/ui/__init__.py',
    'lewisham_walks/ui/icons.py',
    'lewisham_walks/ui/layout.py',
    'lewisham_walks/ui/main_window.py',
    'lewisham_walks/ui/map_widget.py',
    'lewisham_walks/ui/discovery_browser_window.py',
    'lewisham_walks/ui/preferences_window.py',
  ],
  install_dir: moduledir / 'ui',
)

install_data(
  'lewisham_walks/ui/shortcuts-window.ui',
  install_dir: moduledir / 'ui',
)

install_data(
  [
    'lewisham_walks/data/freddys_blossom_walk.json',
    'lewisham_walks/data/listed_buildings.json',
    'lewisham_walks/data/plaques.json',
  ],
  install_dir: moduledir / 'data',
)
