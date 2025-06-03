from fastapi import FastAPI, File, UploadFile, HTTPException, status
# from fastapi.staticfiles import StaticFiles

import base64
from PIL import Image
from io import BytesIO



app =  FastAPI()
# app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {
        "message" : "Connected to FastAPI backend!!!"
    }


@app.post("/upload")
async def upload_func( file: UploadFile = File(...)):
    # base64_string = data["base64"]
    # valid_types = ["gen", "fill"]
    try:
        # if type.lower() not in valid_types:
        #     raise HTTPException(
        #         status_code=status.HTTP_406_NOT_ACCEPTABLE,
        #         detail="not a valid folder type, should be gen / fill!!"
        #     )

        # save_name = f"static/{type.lower()}/{file.filename}"
        save_name = f"/workspace/ComfyUI/input/{file.filename}"
        contents = await file.read()
        pil_image = Image.open(BytesIO(contents))
        pil_image.save(save_name, "PNG")
        return {
            "message" : f"http://192.168.0.84:8000/{save_name}",
            "filename": file.filename, 
            "content_type": file.content_type
        }
    except Exception as e:
        print(e)