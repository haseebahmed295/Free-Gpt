import bpy
import bpy.props
from .dependencies import Module_Updater
from .ui_op import G4F_OT_ClearChat , G4T_Del_Message , G4F_OT_ShowCode
from .prompt_op import G4F_OT_Callback, G4F_TEST_OT_TestModels

no_dep = False
try:
    import g4f.models
except ModuleNotFoundError:
    no_dep = True

class Chat_PT_history(bpy.types.Panel):
    bl_label = "Chat History"
    bl_idname = "G4T_PT_History"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Free Gpt'

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)
        column.enabled = not Module_Updater.is_working and not no_dep
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
    
        if Module_Updater.is_working:
            column.label(text="Updating Dependencies..." , icon="ERROR")
        elif no_dep:
            column.label(text="Dependencies not installed" , icon="ERROR")

class G4f_PT_main(bpy.types.Panel):
    bl_label = "Assistant GPT"
    bl_idname = "G4T_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Free Gpt'

    def draw(self, context):
        layout = self.layout
        column = layout.column()
        column.enabled = not Module_Updater.is_working and not no_dep
        
        # Model selection
        row = column.row(align=True)
        row.label(text="GPT Model:")
        row.operator(G4F_TEST_OT_TestModels.bl_idname, icon="FORCE_CHARGE", text="")
        column.prop(context.scene, "ai_models", text="")

        # Chat input
        column.label(text="Enter your message:")
        column.prop(context.scene, "g4f_chat_input", text="")
        
        column.scale_y = 1.25
        
        # Button
        button_label = "Please wait..." if context.scene.g4f_button_pressed else "Prompt"
        row = column.row(align=True)
        row.operator(G4F_OT_Callback.bl_idname, text=button_label)
        
        # Progress indicator with dynamic text
        if context.scene.g4f_button_pressed:
            column.separator()
            progress = context.scene.g4f_progress
            
            # Determine status text based on progress
            if progress <= 0.0:
                status_text = "Initializing..."
            elif progress <= 0.1:
                status_text = "Preparing request..."
            elif progress <= 0.7:
                status_text = "Generating response..." if context.scene.ai_models in g4f.models.ModelUtils.convert and g4f.models.ModelUtils.convert[context.scene.ai_models].best_provider.supports_stream else "Waiting for response..."
            elif progress <= 0.8:
                status_text = "Processing response..."
            elif progress <= 0.9:
                status_text = "Finalizing..."
            else:
                status_text = "Generation Complete!"
            
            # Display progress bar and text
            if progress < 1.0:
                layout.progress(text=status_text, factor=progress , type='BAR')
            else:
                layout.label(text=status_text)
        
        if Module_Updater.is_working:
            column.label(text="Updating Dependencies..." , icon="ERROR")
        elif no_dep:
            column.label(text="Dependencies not installed" , icon="ERROR")
