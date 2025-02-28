
import bpy
import bpy.props
from .dependencies import Module_Updater
from .ui_op import G4F_OT_ClearChat , G4T_Del_Message , G4F_OT_ShowCode
from .prompt_op import G4F_OT_Callback, G4F_TEST_OT_TestModels
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
        row = column.row(align=True)
        row.label(text="GPT Model:")
        row.operator(G4F_TEST_OT_TestModels.bl_idname , icon="FORCE_CHARGE" , text="")
        column.prop(context.scene, "ai_models", text="")

        column.label(text="Enter your message:")
        column.prop(context.scene, "g4f_chat_input", text="")
        
        column.scale_y = 1.25
        
        button_label = "Please wait..." if context.scene.g4f_button_pressed else "Prompt"
        row = column.row(align=True)
        row.operator(G4F_OT_Callback.bl_idname, text=button_label)
        column.separator()
        layout.progress(factor=0.75, type="RING", text="Generating...")
        
