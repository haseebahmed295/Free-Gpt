
import re
import traceback
import bpy
import bpy.props
import threading
import inspect
import sys
import g4f

from .dependencies import Module_Updater
from .response import *
from .get_models import *
bl_info = {
    "name": "Free Gpt",
    "blender": (4, 2, 0),
    "category": "Object",
    "author": "haseebahmed295",
    "version": (1, 2, 2),
    "location": "3D View > UI > Free Gpt",
    "description": "Automate Blender using GPT without an API key.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
}

from .system_commad import system_prompt


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

class G4F_OT_Callback(bpy.types.Operator):
    bl_idname = "g4f.callback"
    bl_label = "Callback for Thread"
    bl_description = "Callback Model Operator"

    @classmethod
    def poll(cls, context):
        return not context.scene.g4f_button_pressed

    def modal(self, context, event: bpy.types.Event) -> set:
        if event.type == 'ESC':
            self.report({'INFO'}, "Aborting...")
            self.is_cancelled = True
            return {'PASS_THROUGH'}

        if event.type == 'TIMER':
            if self.is_cancelled and self.cancel_done:
                context.scene.g4f_button_pressed = False
                if self.error:
                    self.report({'ERROR'}, str(self.error))
                self.report({'INFO'}, "Aborted Successfully")
                return {'CANCELLED'}
            if self.is_done and not self.is_cancelled:
                self.callback(context, self.code_buffer)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        context.scene.g4f_button_pressed = True
        self.is_done = False
        self.code_buffer = None
        self.is_cancelled = False
        self.cancel_done = False
        self.error = None

        ai_model = context.scene.ai_models
        chat_input = context.scene.g4f_chat_input
        chat_history = context.scene.g4f_chat_history

        threading.Thread(target=self.generate_g4f_code, args=(
            chat_input, chat_history, ai_model, system_prompt
        )).start()

        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        self.report({'INFO'}, 'Generating... (ESC=Abort)')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def generate_g4f_code(self, prompt, chat_history, model, system_prompt):
        formatted_messages = [{"role": "system", "content": system_prompt}]
        for message in chat_history[-10:]:
            role = "assistant" if message.type == "assistant" else message.type.lower()
            content = f"```\n{message.content}\n```" if message.type == "assistant" else message.content
            formatted_messages.append({"role": role, "content": content})
        formatted_messages.append({"role": "user", "content": wrap_prompt(prompt)})

        stream = g4f.models.ModelUtils.convert[model].best_provider.supports_stream

        try:
            if stream:
                completion_text = ''
                for chunk in stream_response(formatted_messages, model):
                    if self.is_cancelled:
                        self.cancel_done = True
                        return
                    completion_text += chunk or ''
                    print(chunk or '', flush=True, end='')
                print("\n")
            else:
                client = g4f.client.Client()
                completion_text = str(client.chat.completions.create(
                    model=model, messages=formatted_messages))
                print(completion_text)

                if self.is_cancelled:
                    self.cancel_done = True
                    return

            code = re.findall(r'```(.*?)```', completion_text, re.DOTALL)[0]
            self.code_buffer = re.sub(r'^python', '', code, flags=re.MULTILINE)
            self.is_done = True

        except Exception as e:
            self.error = e
            print("Canceling...", e)
            self.is_cancelled = True
            self.cancel_done = True

    def callback(self, context, output):
        if self.is_cancelled:
            self.cancel_done = True
            return

        blender_code = output
        message = context.scene.g4f_chat_history.add()
        message.type = 'user'
        message.content = context.scene.g4f_chat_input
        context.scene.g4f_chat_input = ""

        if blender_code:
            global_namespace = globals().copy()
            try:
                override = bpy.context.copy()
                override["selected_objects"] = list(bpy.context.scene.objects)
                with context.temp_override(**override):
                    exec(blender_code, global_namespace)
            except Exception as e:
                self.report({'ERROR'}, f"Error executing code from AI: {e}")
                error = traceback.format_exc()
                blender_code = append_error_as_comment(blender_code, error)
            finally:
                message = context.scene.g4f_chat_history.add()
                message.type = 'assistant'
                message.content = blender_code

        context.scene.g4f_button_pressed = False

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)

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

        editor_area = next((area for area in context.screen.areas if area.type == 'TEXT_EDITOR'), None)

        if editor_area is None:
            editor_area = split_area_to_text_editor(context)

        editor_area.spaces.active.text = code_text
        bpy.ops.text.jump(line=1)

        return {'FINISHED'}

class G4FPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__


    def draw(self, context):
        layout = self.layout
        col = layout.column()
        if bpy.app.online_access:
            current_version = g4f.version.utils.current_version
            latest_version = g4f.version.utils.latest_version
            col.label(text=f"Current Version: {current_version}")
            col.label(text=f"Latest Version: {latest_version}")
            if current_version != latest_version:
                row = col.row()
                row.label(text="New version available")
                text = "Update Dependencies" if not Module_Updater.is_working else "Updating..."
                row.operator(Module_Updater.bl_idname, text=text)
            else:
                col.label(text="You are up to date")
        else:
            col.label(text="No internet connection")
    
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

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.g4f_chat_history
    del bpy.types.Scene.g4f_chat_input
    del bpy.types.Scene.g4f_button_pressed


if __name__ == "__main__":
    register()
