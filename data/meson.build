application_id = 'com.nedrichards.lewishamwalks'

desktop_conf = configuration_data()
desktop_conf.set('APP_EXEC', application_id)
desktop_conf.set('APP_ICON', application_id)

configure_file(
  input: 'com.nedrichards.lewishamwalks.desktop.in',
  output: 'com.nedrichards.lewishamwalks.desktop',
  configuration: desktop_conf,
  install: true,
  install_dir: get_option('datadir') / 'applications',
)

configure_file(
  input: 'com.nedrichards.lewishamwalks.metainfo.xml.in',
  output: 'com.nedrichards.lewishamwalks.metainfo.xml',
  copy: true,
  install: true,
  install_dir: get_option('datadir') / 'metainfo',
)

install_data(
  'com.nedrichards.lewishamwalks.gschema.xml',
  install_dir: get_option('datadir') / 'glib-2.0' / 'schemas',
)

install_data(
  'icons/hicolor/scalable/apps/com.nedrichards.lewishamwalks.svg',
  install_dir: get_option('datadir') / 'icons' / 'hicolor' / 'scalable' / 'apps',
)

service_conf = configuration_data()
service_conf.set('bindir', get_option('prefix') / get_option('bindir'))
configure_file(
  input: 'com.nedrichards.lewishamwalks.service.in',
  output: 'com.nedrichards.lewishamwalks.service',
  configuration: service_conf,
  install_dir: get_option('datadir') / 'dbus-1' / 'services',
)
