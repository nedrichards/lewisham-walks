project(
  'lewisham-walks',
  version: '0.1.0',
  meson_version: '>= 1.0.0',
  default_options: ['warning_level=2', 'werror=false'],
)

i18n = import('i18n')
gnome = import('gnome')

# Keep source builds on the same GTK/libadwaita baseline as the GNOME 51 Flatpak.
dependency('gtk4', version: '>= 4.24.0')
dependency('libadwaita-1', version: '>= 1.10.0')

subdir('data')
subdir('src')
subdir('tests')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)

install_data(
  'COPYING',
  'DATA_SOURCES.md',
  install_dir: get_option('datadir') / 'licenses' / 'com.nedrichards.lewishamwalks',
)
