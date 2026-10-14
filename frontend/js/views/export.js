/** Download admin CSV using the current session, not a bare unauthenticated link. */
export function bindReportExport() {
  const link=document.querySelector('a[href="/api/export/reports"]');
  if (!link) return;
  link.addEventListener('click', async event => {
    event.preventDefault();
    const token=localStorage.getItem('vietsafe_token');
    if (!token) {
      window.alert('Vui lòng đăng nhập với quyền quản trị viên để xuất CSV.');
      return;
    }
    try {
      const response=await fetch('/api/export/reports',{
        headers:{'X-VietSafe':'local','X-VietSafe-Session':token}
      });
      if (!response.ok) {
        const error=await response.json();
        throw new Error(error.error || 'Không thể xuất dữ liệu.');
      }
      const url=URL.createObjectURL(await response.blob());
      const download=document.createElement('a');
      download.href=url;
      download.download='vietsafe-reports.csv';
      document.body.appendChild(download);
      download.click();
      download.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch (error) {
      window.alert(error.message);
    }
  });
}
