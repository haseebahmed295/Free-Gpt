
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

from .dependencies import Module_Updater
from .get_models import get_models
from .ui_op import G4F_OT_ClearChat, G4F_OT_ShowCode ,G4T_Del_Message 
from .interface import Chat_PT_history,G4f_PT_main , G4FPreferences
from .prompt_op import G4F_OT_Callback
import bpy
import bpy.props
import g4f

    
classes = [
    Chat_PT_history,
    G4f_PT_main,
    G4F_OT_ClearChat,
    G4F_OT_Callback,
    G4T_Del_Message,
    G4F_OT_ShowCode,
    G4FPreferences,
    Module_Updater,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.g4f_chat_history = bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    bpy.types.Scene.ai_models = bpy.props.EnumProperty(
        name="AI Model",
        description="Select the AI model to use",
        items=get_models(),
    )
    bpy.types.Scene.g4f_chat_input = bpy.props.StringProperty(
        name="Message",
        description="Enter your Command",
        default="",
    )
    bpy.types.PropertyGroup.type = bpy.props.StringProperty()
    bpy.types.PropertyGroup.content = bpy.props.StringProperty()
    bpy.types.Scene.g4f_button_pressed = bpy.props.BoolProperty()
    
    if bpy.app.online_access:
        update = not (g4f.version.utils.current_version == g4f.version.utils.latest_version)
    else:
        update = False
    bpy.types.Scene.g4f_check_update = bpy.props.BoolProperty(default=update)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.g4f_chat_history
    del bpy.types.Scene.g4f_chat_input
    del bpy.types.Scene.g4f_button_pressed


if __name__ == "__main__":
    register()
