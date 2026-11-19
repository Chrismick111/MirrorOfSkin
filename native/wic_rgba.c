#define COBJMACROS
#define INITGUID
#include <windows.h>
#include <wincodec.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "wic_rgba.h"

void wic_rgba_free(WicRgba *image){if(image){free(image->pixels);memset(image,0,sizeof(*image));}}
int wic_rgba_flip_vertical(WicRgba *image){
 if(!image||!image->pixels||!image->width||!image->height||image->width>UINT_MAX/4||image->stride!=image->width*4||image->height>SIZE_MAX/image->stride||image->size!=(size_t)image->stride*image->height)return 0;
 if(image->height==1)return 1;
 uint8_t *row=malloc(image->stride);if(!row)return 0;
 for(uint32_t y=0;y<image->height/2;y++){
  uint8_t *top=image->pixels+(size_t)y*image->stride;
  uint8_t *bottom=image->pixels+(size_t)(image->height-1-y)*image->stride;
  memcpy(row,top,image->stride);memcpy(top,bottom,image->stride);memcpy(bottom,row,image->stride);
 }
 free(row);return 1;
}

int wic_rgba_decode(const void *png,size_t length,WicRgba *out){
 static const unsigned char magic[]={137,80,78,71,13,10,26,10};
 IWICImagingFactory *factory=NULL;IWICStream *stream=NULL;IWICBitmapDecoder *decoder=NULL;
 IWICBitmapFrameDecode *frame=NULL;IWICFormatConverter *converter=NULL;
 uint8_t *pixels=NULL;UINT w=0,h=0,stride=0,total=0;int initialized=0,ok=0;
 if(!png||!out||out->pixels||length<sizeof(magic)||length>UINT_MAX||memcmp(png,magic,sizeof(magic)))return 0;
 HRESULT hr=CoInitializeEx(NULL,COINIT_MULTITHREADED);
 if(SUCCEEDED(hr))initialized=1;else if(hr!=RPC_E_CHANGED_MODE)return 0;
 hr=CoCreateInstance(&CLSID_WICImagingFactory,NULL,CLSCTX_INPROC_SERVER,&IID_IWICImagingFactory,(void**)&factory);if(FAILED(hr))goto done;
 hr=IWICImagingFactory_CreateStream(factory,&stream);if(FAILED(hr))goto done;
 hr=IWICStream_InitializeFromMemory(stream,(BYTE*)png,(DWORD)length);if(FAILED(hr))goto done;
 hr=IWICImagingFactory_CreateDecoderFromStream(factory,(IStream*)stream,NULL,WICDecodeMetadataCacheOnLoad,&decoder);if(FAILED(hr))goto done;
 GUID container;hr=IWICBitmapDecoder_GetContainerFormat(decoder,&container);if(FAILED(hr)||!IsEqualGUID(&container,&GUID_ContainerFormatPng))goto done;
 hr=IWICBitmapDecoder_GetFrame(decoder,0,&frame);if(FAILED(hr))goto done;
 hr=IWICBitmapFrameDecode_GetSize(frame,&w,&h);if(FAILED(hr)||!w||!h||w>UINT_MAX/4)goto done;
 stride=w*4;if(h>UINT_MAX/stride)goto done;total=stride*h;
 hr=IWICImagingFactory_CreateFormatConverter(factory,&converter);if(FAILED(hr))goto done;
 hr=IWICFormatConverter_Initialize(converter,(IWICBitmapSource*)frame,&GUID_WICPixelFormat32bppRGBA,WICBitmapDitherTypeNone,NULL,0,WICBitmapPaletteTypeCustom);if(FAILED(hr))goto done;
 pixels=malloc(total);if(!pixels)goto done;
 hr=IWICFormatConverter_CopyPixels(converter,NULL,stride,total,pixels);if(FAILED(hr))goto done;
 *out=(WicRgba){pixels,w,h,stride,total};pixels=NULL;ok=1;
done:
 free(pixels);if(converter)IWICFormatConverter_Release(converter);if(frame)IWICBitmapFrameDecode_Release(frame);
 if(decoder)IWICBitmapDecoder_Release(decoder);if(stream)IWICStream_Release(stream);if(factory)IWICImagingFactory_Release(factory);
 if(initialized)CoUninitialize();return ok;
}
