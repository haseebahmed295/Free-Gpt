import logging
import os
import bpy
import g4f
import g4f.client
g4f.debug.version_check = False
def wrap_prompt(prompt):
    wrapped = f"""{prompt} . Don't write code which uses bpy.context.active_object.Make sure to return all code in only one code blocks 
    """
    return wrapped

def split_area_to_text_editor(context):
    area = context.area
    for region in area.regions:
        if region.type == 'WINDOW':
            with context.temp_override(area=area, region=region):
                # bpy.ops.screen.area_split(direction='VERTICAL', factor=0.5)
                bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
            break

    new_area = context.screen.areas[-1]
    new_area.type = 'TEXT_EDITOR'
    return new_area

def append_error_as_comment(code_str, error):
    error_lines = str(error).splitlines()
    commented_error = "\n".join("# " + line for line in error_lines)
    updated_code = code_str + "\n # Code Output:\n" + commented_error
    return updated_code

def stream_response(message , model):
    client = g4f.client.Client()
    response = client.chat.completions.create(
        model=model,
        messages=message,
        stream=True,
    )
    for message in response:
        yield message.choices[0].delta.content

def setup_logger():
    log_path = os.path.join(os.path.dirname(__file__), 'g4f_callback.log')
    logging.basicConfig(
        level=logging.DEBUG,    
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=log_path
    )
    logging.getLogger('markdown_it').setLevel(logging.WARNING)  # Silence Markdown parsing logs
    logging.getLogger('rich').setLevel(logging.WARNING)  # Silence rich internal logs
    
    return logging.getLogger('G4F_Callback')