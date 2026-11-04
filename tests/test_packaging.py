import unittest

from build_mac import deployment_versions


class DeploymentTargetTests(unittest.TestCase):
    def test_build_version_does_not_use_linker_or_sdk_version(self):
        output = """example:
Load command 10
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform MACOS
    minos 11.0
      sdk 26.5
   ntools 1
     tool LD
  version 1267.0
"""
        self.assertEqual(list(deployment_versions(output)), [(11, 0)])

    def test_legacy_deployment_command_and_universal_slices(self):
        output = """example (architecture x86_64):
Load command 9
      cmd LC_VERSION_MIN_MACOSX
  cmdsize 16
  version 10.13
      sdk 12.1
example (architecture arm64):
Load command 9
      cmd LC_BUILD_VERSION
    minos 11.0
      sdk 12.1
"""
        self.assertEqual(list(deployment_versions(output)), [(10, 13), (11, 0)])
