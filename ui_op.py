import bpy
from .utils import split_area_to_text_editor

class G4F_OT_ClearChat(bpy.types.Operator):
    bl_idname = "g4f.clear_whole_chat"
    bl_label = "Clear Chat"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return False if len(context.scene.g4f_chat_history) ==0 else True
    def execute(self, context):
        context.scene.g4f_chat_history.clear()
        return {'FINISHED'}

class G4T_Del_Message(bpy.types.Operator):
    bl_idname = "g4f.del_message"
    bl_label = "Delete Message from History"
    bl_options = {'REGISTER', 'UNDO'}

    index : bpy.props.IntProperty(options={'HIDDEN'})

    def execute(self, context):
        context.scene.g4f_chat_history.remove(self.index)
        context.scene.g4f_chat_history.remove(self.index)
        return {'FINISHED'}

class G4F_OT_ShowCode(bpy.types.Operator):
    bl_idname = "g4f.show_code"
    bl_label = "Show Code"
    bl_options = {'REGISTER', 'UNDO'}

    code:bpy.props.StringProperty(
        name="Code",
        description="The generated code",
        default="",
    )

    def execute(self, context):
        code_name = "G4F_Code.py"
        code_text = bpy.data.texts.get(code_name)
        if code_text is None:
            code_text = bpy.data.texts.new(code_name)

        code_text.clear()
        code_text.write(self.code)

        editor_area = split_area_to_text_editor(context)

        editor_area.spaces.active.text = code_text
        bpy.ops.text.jump(line=1)

        return {'FINISHED'}

