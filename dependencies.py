import re
import subprocess
import sys
import bpy
import threading
import os
from .utils import create_models, setup_logger
from .import toml

Modules = ["g4f", "rich"]

class Module_Updater(bpy.types.Operator):
    bl_idname = "g4f.module_update"
    bl_label = "Module Updater"
    bl_description = "Update the modules"
    bl_options = {'REGISTER', 'UNDO'}

    is_working: bool = False

    @classmethod
    def poll(cls, context):
        """Ensure installation can be performed only when no other installation is in progress."""
        return not Module_Updater.is_working and not context.scene.g4f_button_pressed

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set:
        """Handle timer events for monitoring installation progress."""
        if event.type == 'TIMER':
            if not self.is_working:
                if self._is_error:
                    self.logger.error("Module update failed")
                    self.report({"ERROR"}, "Update Failed")
                else:
                    self.logger.info("Reloading modules after successful update")
                    self.report({"INFO"}, "Reloading Modules...")
                Module_Updater.is_working = False
                bpy.app.timers.register(self.reload, first_interval=2)
                self.logger.info("Module update completed")
                self.report({"INFO"}, "Update Done")
                return {'FINISHED'}

        return {'PASS_THROUGH'}
        
    def execute(self, context):
        self.logger = setup_logger()
        self.logger.info("Starting module update operation")
        
        """Execute the installation process with validation checks."""
        if not bpy.app.online_access:
            self.logger.error("No internet connection available")
            self.report({"ERROR"}, "No internet connection")
            return {'CANCELLED'}
            
        self._is_error = False
        Module_Updater.is_working = True
        toml_path = os.path.join(os.path.dirname(__file__), "blender_manifest.toml")
        wheels_path = os.path.join(os.path.dirname(__file__), "wheels")
        
        self.logger.debug(f"Configuration - TOML path: {toml_path}, Wheels path: {wheels_path}")
        
        # Start the updating thread
        module_thread = threading.Thread(
            target=self.install_modules,
            args=(Modules, wheels_path, toml_path)
        )
        module_thread.start()
        self.logger.info("Started module update thread")
        self.report({"INFO"}, "Updating Modules... 😎")
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
        
    def install_modules(self, module_name, wheels_path, toml_path):
        """Install the specified modules and update the TOML configuration."""
        self.logger.info(f"Installing modules: {module_name}")
        wheel_list = self.download_wheels(module_name, wheels_path)
        if not wheel_list:
            self.logger.error("No wheels downloaded, installation failed")
            self._is_error = True
            self.is_working = False
            Module_Updater.is_working = False
            return
        self.logger.info(f"Successfully downloaded {len(wheel_list)} wheel(s)")
        self.manage_modules(wheel_list, wheels_path, toml_path)
        self.is_working = False
        self.logger.info("Module installation process completed")
        return
    
    def manage_modules(self, module_list, wheels_path, toml_path):
        """Manage downloaded wheels and update manifest."""
        self.logger.debug(f"Managing {len(module_list)} modules in {wheels_path}")
        
        if not os.path.isdir(wheels_path):
            os.makedirs(wheels_path, exist_ok=True)
            self.logger.info(f"Created wheels directory: {wheels_path}")
            
        if not module_list:
            self.logger.warning("No modules to manage")
            return
            
        a_wheels, r_wheels = self.process_wheel_files(module_list, wheels_path)
        
        for wheel in r_wheels:
            wheel_path = os.path.join(wheels_path, wheel)
            if os.path.exists(wheel_path):
                os.remove(wheel_path)
                self.logger.debug(f"Removed old wheel: {wheel}")
                
        self.append_wheel(toml_path, a_wheels, wheels_path)
        self.logger.info(f"Updated manifest with {len(a_wheels)} wheels")

    def parse_wheel_filename(self, filename):
        """Parse wheel filename into components."""
        pattern = r"^(?P<package>[^-]+)-(?P<version>[^-]+)(-(?P<build>\d[^-]*))?-(?P<python_tag>[^-]+)-(?P<abi_tag>[^-]+)-(?P<platform>[^.]+)\.whl$"
        match = re.match(pattern, filename)
        if not match:
            self.logger.error(f"Invalid wheel filename format: {filename}")
            raise ValueError(f"Invalid wheel filename format: {filename}")
        self.logger.debug(f"Parsed wheel filename: {filename}")
        return match.groupdict()

    def process_wheel_files(self, wheel_list, wheels_path, target_python_version='cp311'):
        """Process wheel files, keeping latest versions and renaming if needed."""
        self.logger.debug(f"Processing {len(wheel_list)} wheel files")
        
        packages = {}
        kept_wheels = []
        removed_wheels = []

        def version_key(version):
            return tuple(map(int, version.split('.')))

        # Group and sort wheels
        for filename in wheel_list:
            parsed = self.parse_wheel_filename(filename)
            pkg = parsed['package']
            if pkg not in packages:
                packages[pkg] = []
            packages[pkg].append((filename, parsed['version']))

        # Process each package
        for package, wheels in packages.items():
            sorted_wheels = sorted(wheels, key=lambda x: version_key(x[1]), reverse=True)
            latest_filename, latest_version = sorted_wheels[0]
            parsed = self.parse_wheel_filename(latest_filename)

            # Check and rename if Python tag doesn't match target
            if parsed['python_tag'] != target_python_version:
                original_path = os.path.join(wheels_path, latest_filename)
                build_part = f"-{parsed['build']}" if parsed['build'] else ""
                new_filename = f"{parsed['package']}-{parsed['version']}{build_part}-{target_python_version}-{parsed['abi_tag']}-{parsed['platform']}.whl"
                new_path = os.path.join(wheels_path, new_filename)
                os.rename(original_path, new_path)
                self.logger.info(f"Renamed wheel: {latest_filename} → {new_filename}")
                kept_wheels.append(new_filename)
            else:
                kept_wheels.append(latest_filename)
                self.logger.debug(f"Kept wheel: {latest_filename}")

            # Mark older versions for removal
            for w in sorted_wheels[1:]:
                removed_wheels.append(w[0])
                self.logger.debug(f"Marked for removal: {w[0]}")

        return kept_wheels, removed_wheels

    def reload(self):
        """Reload Blender scripts and update module list."""
        self.logger.info("Reloading Blender scripts")
        bpy.ops.script.reload()
        create_models()
    
    def append_wheel(self, file_path, module_list, wheels_path):
        """Append wheel entries to TOML configuration."""
        self.logger.debug(f"Appending wheels to TOML: {file_path}")
        try:
            config = {}
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    config = toml.load(f)
            config.setdefault('wheels', [])
            existing_wheels = set(config['wheels'])
            for module in module_list:
                wheel_name = os.path.join("./wheels", module).replace("\\", "/")
                if wheel_name not in existing_wheels:
                    config['wheels'].append(wheel_name)
                    self.logger.debug(f"Added wheel to TOML: {wheel_name}")
            with open(file_path, 'w') as f:
                toml.dump(config, f)
            self.logger.info("Successfully updated TOML configuration")
        except Exception as e:
            self.logger.error(f"Error updating TOML: {str(e)}")
            self._is_error = True

    def download_wheels(self, module_name: list, output_dir):
        """Download the module's wheel files with real-time logging."""
        self.logger.info(f"Downloading wheels for modules: {module_name}")
        try:
            os.makedirs(output_dir, exist_ok=True)
            self.logger.debug(f"Ensured output directory exists: {output_dir}")
            
            command = [sys.executable, "-m", "pip", "download"]
            command.extend(module_name)
            command.append(f"--dest={output_dir}")
            self.logger.debug(f"Executing command: {' '.join(command)}")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            while process.poll() is None:
                line = process.stdout.readline()
                if line:
                    self.logger.debug(f"pip output: {line.strip()}")
                    print(line.strip())
            
            if process.returncode != 0:
                self.logger.error(f"Download failed with exit code: {process.returncode}")
                self._is_error = True
                return []
            
            wheel_files = [f for f in os.listdir(output_dir) if f.endswith('.whl')]
            if not wheel_files:
                self.logger.error(f"No wheel files found for {module_name}")
                self._is_error = True
                return []
            
            self.logger.info(f"Successfully downloaded wheels: {wheel_files}")
            return wheel_files
        
        except Exception as e:
            self.logger.error(f"Error during wheel download: {str(e)}")
            self._is_error = True
            return []
