/** Send JSON requests to the local server using the VietSafe CSRF header. */
export function createApi(getToken) {
  return async function api(path, options={}) {
    const controller=new AbortController();
    const {timeoutMs=12000,...requestOptions}=options;
    const timeout=setTimeout(()=>controller.abort(),timeoutMs);
    const token=getToken();
    const authHeaders=token ? {'X-VietSafe-Session':token} : {};
    try {
      const response=await fetch(path,{...requestOptions,signal:controller.signal,headers:{'X-VietSafe':'local',...authHeaders,...(requestOptions.body?{'Content-Type':'application/json'}:{}),...requestOptions.headers}});
      const data=await response.json();
      if(!response.ok) throw new Error(data.error || 'Không thể xử lý yêu cầu.');
      return data;
    } catch(e) {if(e.name==='AbortError') throw new Error('Máy chủ phản hồi chậm. Hãy thử lại.'); throw e;}
    finally {clearTimeout(timeout);}
  };
}
