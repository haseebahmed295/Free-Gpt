
bl_info = {
    "name": "Free Gpt",
    "blender": (4, 2, 0),
    "category": "Object",
    "author": "haseebahmed295",
    "version": (1, 3, 0),
    "location": "3D View > UI > Free Gpt",
    "description": "Automate Blender using GPT without an API key.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
}

if "bpy" in locals():
    import importlib
    importlib.reload(bpy)
    importlib.reload(utils)
    importlib.reload(dependencies)
    importlib.reload(ui_op)
    importlib.reload(interface)
    importlib.reload(prompt_op)

from .utils import create_models
from .dependencies import Module_Updater
from .ui_op import G4F_OT_ClearChat, G4F_OT_ShowCode ,G4T_Del_Message 
from .interface import Chat_PT_history,G4f_PT_main 
from .prompt_op import G4F_OT_Callback , G4F_TEST_OT_TestModels
import bpy

no_dep = False
try:
    import g4f
except ModuleNotFoundError:
    no_dep = True

class G4FPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        if no_dep:
            col.label(text="Dependencies not installed")
            col.label(text="Install dependencies to use this add-on")
            col.operator(Module_Updater.bl_idname, text="Install Dependencies")
            return
        
        if bpy.app.online_access:
            try:
                is_update = g4f.version.utils.current_version != g4f.version.utils.latest_version
            except:
                is_update = False
            if is_update:
                row = col.row()
                row.label(text="New version available")
                text = "Update Dependencies" if not Module_Updater.is_working else "Updating..."
                row.operator(Module_Updater.bl_idname, text=text)
            else:
                col.label(text="You are up to date")
            
        else:
            col.label(text="No internet connection")

classes = [
    G4FPreferences,
    Chat_PT_history,
    G4f_PT_main,
    G4F_OT_ClearChat,
    G4F_OT_Callback,
    G4T_Del_Message,
    G4F_OT_ShowCode,
    Module_Updater,
    G4F_TEST_OT_TestModels
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.g4f_chat_history = bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    create_models()
    bpy.types.Scene.g4f_chat_input = bpy.props.StringProperty(
        name="Message",
        description="Enter your Command",
        default="",
    )
    bpy.types.Scene.g4f_progress = bpy.props.FloatProperty(
        name="Generation Progress",
        description="Progress of the AI generation task",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='PERCENTAGE'
    )
    bpy.types.PropertyGroup.type = bpy.props.StringProperty()
    bpy.types.PropertyGroup.content = bpy.props.StringProperty()
    bpy.types.Scene.g4f_button_pressed = bpy.props.BoolProperty()
    


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.g4f_progress
    del bpy.types.Scene.g4f_chat_history
    del bpy.types.Scene.g4f_chat_input
    del bpy.types.Scene.g4f_button_pressed


if __name__ == "__main__":
    register()
