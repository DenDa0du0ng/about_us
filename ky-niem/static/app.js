(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  /* ---- Xem ảnh lớn ---- */
  const lb = $('#lightbox');
  const lbImg = $('img', lb);
  const lbCap = $('figcaption', lb);
  let links = [], idx = 0;

  function show(i) {
    idx = (i + links.length) % links.length;
    lbImg.src = links[idx].href;
    lbCap.textContent = `${links[idx].dataset.caption || ''}  (${idx + 1}/${links.length})`;
  }
  function openLb(i) { lb.hidden = false; document.body.style.overflow = 'hidden'; show(i); }
  function closeLb() { lb.hidden = true; lbImg.src = ''; document.body.style.overflow = ''; }

  document.addEventListener('click', e => {
    const a = e.target.closest('a.ph');
    if (a) { e.preventDefault(); links = $$('a.ph'); openLb(links.indexOf(a)); return; }
    if (e.target.closest('.lb-close') || e.target === lb) closeLb();
    if (e.target.closest('.lb-prev')) show(idx - 1);
    if (e.target.closest('.lb-next')) show(idx + 1);
  });
  document.addEventListener('keydown', e => {
    if (lb.hidden) return;
    if (e.key === 'Escape') closeLb();
    if (e.key === 'ArrowLeft') show(idx - 1);
    if (e.key === 'ArrowRight') show(idx + 1);
  });
  let startX = null;
  lb.addEventListener('touchstart', e => { startX = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener('touchend', e => {
    if (startX === null) return;
    const dx = e.changedTouches[0].clientX - startX;
    if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1));
    startX = null;
  });

  /* ---- Xóa một ảnh ---- */
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-del]');
    if (!btn) return;
    if (!confirm('Xóa ảnh này? Không thể khôi phục.')) return;
    const res = await fetch(btn.dataset.del, { method: 'POST' });
    if (res.ok) btn.closest('.tile').remove();
    else alert('Không xóa được ảnh, hãy thử lại.');
  });

  /* ---- Tải ảnh lên theo từng nhóm nhỏ (chịu được hàng trăm ảnh) ---- */
  const MAX_BATCH_FILES = 6;
  const MAX_BATCH_BYTES = 60 * 1024 * 1024;

  function sendBatch(memoryId, batch, onBytes) {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      batch.forEach(f => fd.append('photos', f, f.name));
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/memories/${memoryId}/photos`);
      xhr.upload.onprogress = ev => { if (ev.lengthComputable) onBytes(ev.loaded); };
      xhr.onload = () => (xhr.status === 200 ? resolve(JSON.parse(xhr.responseText)) : reject(new Error('Máy chủ từ chối ảnh.')));
      xhr.onerror = () => reject(new Error('Mất kết nối khi tải ảnh.'));
      xhr.send(fd);
    });
  }

  window.MemUpload = {
    async upload(memoryId, files, onProgress) {
      const total = files.length;
      const totalBytes = files.reduce((s, f) => s + f.size, 0) || 1;
      let doneFiles = 0, doneBytes = 0, i = 0;
      while (i < files.length) {
        const batch = [];
        let bytes = 0;
        while (i < files.length && batch.length < MAX_BATCH_FILES && (batch.length === 0 || bytes + files[i].size <= MAX_BATCH_BYTES)) {
          bytes += files[i].size; batch.push(files[i]); i++;
        }
        await sendBatch(memoryId, batch, loaded => {
          onProgress(doneFiles, total, Math.min(100, ((doneBytes + loaded) / totalBytes) * 100));
        });
        doneFiles += batch.length; doneBytes += bytes;
        onProgress(doneFiles, total, (doneBytes / totalBytes) * 100);
      }
    }
  };
})();
