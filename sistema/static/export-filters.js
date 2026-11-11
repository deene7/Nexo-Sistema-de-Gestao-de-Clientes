(function () {
  'use strict';
  const form = document.querySelector('[data-export-filters]');
  if (!form) return;
  const count = document.querySelector('[data-export-count]');
  const status = document.querySelector('[data-export-status]');
  const summary = document.querySelector('[data-export-summary]');
  let timer, controller, version = 0;
  async function update(current) {
    controller = new AbortController();
    try {
      const query = new URLSearchParams(new FormData(form));
      const response = await fetch(form.dataset.countUrl + '?' + query, {
        signal: controller.signal, headers: {Accept: 'application/json'}, cache: 'no-store'
      });
      if (!response.ok || response.redirected) throw new Error('count');
      const data = await response.json();
      if (!Number.isInteger(data.total) || data.total < 0) throw new Error('count');
      if (current !== version) return;
      count.textContent = data.total.toLocaleString('pt-BR');
      status.textContent = data.total === 0 ? 'Nenhum cliente encontrado' :
        data.filtrado ? 'Com filtros aplicados' : 'Todos os clientes ativos';
    } catch (error) {
      if (current !== version) return;
      count.textContent = '—';
      status.textContent = 'Não foi possível contar. Altere os filtros ou atualize a página para tentar novamente.';
    } finally {
      if (current === version) summary.removeAttribute('aria-busy');
    }
  }
  function schedule() {
    clearTimeout(timer);
    if (controller) controller.abort();
    const current = ++version;
    count.textContent = '…';
    status.textContent = 'Contando clientes…';
    summary.setAttribute('aria-busy', 'true');
    timer = setTimeout(() => update(current), 250);
  }
  form.addEventListener('change', schedule);
  form.addEventListener('reset', schedule);
  schedule();
})();
