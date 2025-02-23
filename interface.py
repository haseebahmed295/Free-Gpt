
import bpy
import bpy.props
from .dependencies import Module_Updater
from .ui_op import G4F_OT_ClearChat , G4T_Del_Message , G4F_OT_ShowCode
from .prompt_op import G4F_OT_Callback
class Chat_PT_history(bpy.types.Panel):
    bl_label = "Chat History"
    bl_idname = "G4T_PT_History"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Free Gpt'

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)
        column.enabled = not Module_Updater.is_working
        column.label(text="Chat history:")
        for index, message in enumerate(context.scene.g4f_chat_history):
            if index % 2 == 0:
                box = column.box()
            row = box.row()
            if message.type == 'assistant':
                row.label(text="Assistant: ")
                code_part = row.operator(G4F_OT_ShowCode.bl_idname, text="Show Code")
                code_part.code = message.content
            else:
                row.label(text=f"User: {message.content}")
            if index % 2 == 0:
                row.operator(G4T_Del_Message.bl_idname, text="", icon="TRASH", emboss=False).index = index
        layout.operator(G4F_OT_ClearChat.bl_idname, text="Clear Chat")
        column.separator()

class G4f_PT_main(bpy.types.Panel):
    bl_label = "Assistant GPT"
    bl_idname = "G4T_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Free Gpt'

    def draw(self, context):
        layout = self.layout
        column = layout.column()
        column.enabled = not Module_Updater.is_working
        column.label(text="GPT Model:")
        column.prop(context.scene, "ai_models", text="")

        column.label(text="Enter your message:")
        column.prop(context.scene, "g4f_chat_input", text="")
        
        column.scale_y = 1.25
        
        button_label = "Please wait..." if context.scene.g4f_button_pressed else "Prompt"
        row = column.row(align=True)
        row.operator(G4F_OT_Callback.bl_idname, text=button_label)
        column.separator()
        layout.progress(factor=0.75, type="RING", text="Generating...")
        
class G4FPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__


    def draw(self, context):
        layout = self.layout
        col = layout.column()
        if bpy.app.online_access:
            if context.scene.g4f_check_update:
                row = col.row()
                row.label(text="New version available")
                text = "Update Dependencies" if not Module_Updater.is_working else "Updating..."
                row.operator(Module_Updater.bl_idname, text=text)
            else:
                col.label(text="You are up to date")
        else:
            col.label(text="No internet connection")