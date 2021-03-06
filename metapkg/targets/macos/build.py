import mimetypes
import os
import pathlib
import stat

from xml.dom import minidom

from metapkg.targets import generic
from metapkg import tools


class Build(generic.Build):

    def _build(self):
        super()._build()
        self._build_installer()

    def _build_installer(self):
        pkg = self._root_pkg
        title = pkg.name
        version = pkg.pretty_version
        ident = f'{pkg.identifier}{pkg.slot_suffix}'

        temp_root = self.get_temp_root(relative_to=None)
        installer = temp_root / 'installer'
        installer.mkdir(parents=True)

        srcdir = self.get_image_root(relative_to=None)

        # Unversioned package.

        selectdir = installer / 'Common'
        selectdir.mkdir(parents=True)

        sysbindir = self.get_install_path('systembin')

        for path, data in self._root_pkg.get_bin_shims(self).items():
            bin_path = (sysbindir / path).relative_to('/')
            inst_path = selectdir / bin_path
            inst_path.parent.mkdir(parents=True, exist_ok=True)
            with open(inst_path, 'w') as f:
                f.write(data)
            os.chmod(inst_path,
                     stat.S_IRWXU | stat.S_IRGRP |
                     stat.S_IXGRP | stat.S_IROTH |
                     stat.S_IXOTH)

        paths_d = selectdir / 'etc' / 'paths.d' / self._root_pkg.identifier
        paths_d.parent.mkdir(parents=True)
        sysbindir = self.get_install_path('systembin')

        with open(paths_d, 'w') as f:
            print(sysbindir, file=f)

        common_pkgname = f'{title}-common.pkg'
        common_pkgpath = installer / common_pkgname

        tools.cmd('pkgbuild',
                  '--root', selectdir,
                  '--identifier', f'{self._root_pkg.identifier}-common',
                  '--version', version,
                  '--install-location', '/',
                  common_pkgpath)

        # Main Versioned Package
        stagemap = {
            'before_install': 'preinstall',
            'after_install': 'postinstall',
        }

        scriptdir = installer / 'Scripts'
        scriptdir.mkdir(parents=True)

        for genstage, inststage in stagemap.items():
            script = self.get_script(genstage, installable_only=True)
            if script:
                with open(scriptdir / inststage, 'w') as f:
                    print('#!/bin/bash\nset -e', file=f)
                    print(script, file=f)
                os.chmod(scriptdir / inststage,
                         stat.S_IRWXU | stat.S_IRGRP |
                         stat.S_IXGRP | stat.S_IROTH |
                         stat.S_IXOTH)

        pkgname = f'{title}{pkg.slot_suffix}.pkg'
        pkgpath = installer / pkgname

        tools.cmd('pkgbuild',
                  '--root', srcdir,
                  '--identifier', ident,
                  '--scripts', scriptdir,
                  '--version', version,
                  '--install-location', '/',
                  pkgpath)

        rsrcdir = installer / 'Resources'
        rsrcdir.mkdir(parents=True)

        resources = self._root_pkg.get_resources(self)

        for name, data in resources.items():
            with open(rsrcdir / name, 'wb') as f:
                data = data.replace(b'$TITLE', pkg.title.encode())
                data = data.replace(b'$FULL_VERSION', version.encode())
                f.write(data)

        distribution = installer / 'Distribution.xml'

        tools.cmd('productbuild',
                  '--package', pkgpath,
                  '--package', common_pkgpath,
                  '--resources', rsrcdir,
                  '--identifier', ident,
                  '--version', version,
                  '--synthesize', distribution)

        dist_xml = minidom.parse(str(distribution))
        gui_xml = dist_xml.documentElement

        for name in resources:
            res_type = pathlib.Path(name).stem.lower()
            if res_type in ('welcome', 'readme', 'license', 'conclusion',
                            'background'):
                mimetype = mimetypes.guess_type(name)
                element = dist_xml.createElement(res_type)
                element.setAttribute('file', name)
                if mimetype[0] is not None:
                    element.setAttribute('mime-type', mimetype[0])
                if res_type == 'background':
                    element.setAttribute('alignment', 'left')

                gui_xml.appendChild(element)

        title_el = dist_xml.createElement('title')
        title_text = dist_xml.createTextNode(pkg.title)
        title_el.appendChild(title_text)
        gui_xml.appendChild(title_el)

        options = gui_xml.getElementsByTagName('options')
        if options:
            options = options[0]
        else:
            options = dist_xml.createElement('options')
            gui_xml.appendChild(options)

        options.setAttribute('customize', 'never')
        options.setAttribute('rootVolumeOnly', 'true')

        with open(distribution, 'w') as f:
            f.write(dist_xml.toprettyxml())

        self._outputroot.mkdir(parents=True, exist_ok=True)

        suffix = self._revision
        if self._subdist:
            suffix = f'{suffix}.{self._subdist}'

        finalname = f'{title}{pkg.slot_suffix}_{version}_{suffix}.pkg'
        tools.cmd('productbuild',
                  '--package-path', pkgpath.parent,
                  '--resources', rsrcdir,
                  '--identifier', ident,
                  '--version', version,
                  '--distribution', distribution,
                  self._outputroot / finalname)

    def _package(self):
        pass
