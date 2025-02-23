import re
import subprocess
import sys
import bpy
from . import toml
import os
import threading
Modules = ["g4f"]

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
        """
        Handle timer events for monitoring installation progress.
        
        Checks every 0.01s for installation status and updates the user on success or failure.
        """
        if event.type == 'TIMER':
            if not self.is_working:
                if self._is_error:
                    self.report({"ERROR"}, "Update Failed")
                else:
                    self.report({"INFO"}, "Reloading Modules...")
                Module_Updater.is_working = False
                bpy.app.timers.register(self.reload, first_interval=2)
                self.report({"INFO"}, "Update Done")
                return {'FINISHED'}

        return {'PASS_THROUGH'}
        
    def execute(self, context):
        """Execute the installation process with validation checks."""
        if not bpy.app.online_access:
            self.report({"ERROR"}, "No internet connection")
            return {'CANCELLED'}
        self._is_error = False
        Module_Updater.is_working = True
        toml_path = os.path.join(os.path.dirname(__file__), "blender_manifest.toml")
        wheels_path = os.path.join(os.path.dirname(__file__), "wheels")
        module = Modules[0]
        # Start the upscaling thread
        module_thread = threading.Thread(
            target=self.install_modules,
            args=(module,wheels_path, toml_path)
        )
        module_thread.start()
        self.report({"INFO"}, "Updating Modules... 😎")
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
        
    def install_modules(self,module_name, wheels_path, toml_path ):
        """Install the specified module and update the TOML configuration."""
        wheel_list = self.download_wheels(module_name, wheels_path)
        if not wheel_list:
            self._is_error = True
            self._is_working = False
            Module_Updater.is_working = False
            return
        self.manage_modules(wheel_list, wheels_path, toml_path)
        self.is_working = False
        return
    
    def manage_modules(self, module_list, wheels_path, toml_path):
        if not os.path.isdir(wheels_path):
            os.makedirs(wheels_path, exist_ok=True)
        if not module_list:
            return
        a_wheels, r_wheels = self.process_wheel_files(module_list, wheels_path)
        for wheel in r_wheels:
            wheel_path = os.path.join(wheels_path, wheel)
            if os.path.exists(wheel_path):
                os.remove(wheel_path)
        self.append_wheel(toml_path, a_wheels, wheels_path)
    def parse_wheel_filename(self, filename):
        # Regular expression to match wheel filename components
        pattern = r"^(?P<package>[^-]+)-(?P<version>[^-]+)(-(?P<build>\d[^-]*))?-(?P<python_tag>[^-]+)-(?P<abi_tag>[^-]+)-(?P<platform>[^.]+)\.whl$"
        match = re.match(pattern, filename)
        if not match:
            raise ValueError(f"Invalid wheel filename format: {filename}")
    
        return match.groupdict()
    def process_wheel_files(self, wheel_list, wheels_path, target_python_version='cp311'):
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
                # Construct new filename, handling optional build tag
                build_part = f"-{parsed['build']}" if parsed['build'] else ""
                new_filename = f"{parsed['package']}-{parsed['version']}{build_part}-{target_python_version}-{parsed['abi_tag']}-{parsed['platform']}.whl"
                new_path = os.path.join(wheels_path, new_filename)
                os.rename(original_path, new_path)
                print(f"Renamed: {latest_filename} → {new_filename}")
                kept_wheels.append(new_filename)
            else:
                kept_wheels.append(latest_filename)

            # Mark older versions for removal
            for w in sorted_wheels[1:]:
                removed_wheels.append(w[0])

        return kept_wheels, removed_wheels
    def reload(self):
        """Reload Blender scripts and update module list."""
        bpy.ops.script.reload()
    
    def append_wheel(self, file_path, module_list, wheels_path):
        try:
            config = {}
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    config = toml.load(f)
            config.setdefault('wheels', [])
            # Avoid duplicates
            existing_wheels = set(config['wheels'])
            for module in module_list:
                wheel_name = os.path.join("./wheels", module).replace("\\", "/")
                if wheel_name not in existing_wheels:
                    config['wheels'].append(wheel_name)
            with open(file_path, 'w') as f:
                toml.dump(config, f)
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            self._is_error = True
 
    def download_wheels(self, module_name, output_dir):
        """Download the module's wheel files and output progress in real-time."""
        try:
            # Ensure the output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            # Construct the pip download command
            command = [sys.executable,"-m","pip", "download", module_name, f"--dest={output_dir}"]
            
            # Start the subprocess with real-time output
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                universal_newlines=True,
                bufsize=1  # Line buffering
            )
            
            # Read and print output in real-time
            while process.poll() is None:  # While the process is running
                line = process.stdout.readline()
                if line:
                    print(line.strip())
            
            # Check the return code after the process completes
            if process.returncode != 0:
                print(f"Error downloading {module_name}: Process exited with code {process.returncode}")
                self._is_error = True
                return []
            
            # Collect wheel files from the output directory
            wheel_files = [f for f in os.listdir(output_dir) if f.endswith('.whl')]
            if not wheel_files:
                print(f"No wheel files found for {module_name}")
                self._is_error = True
                return []
            
            return wheel_files
        
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            self._is_error = True
            return []