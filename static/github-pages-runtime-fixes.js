(() => {
  'use strict';

  if (!/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const previousFetch = window.fetch.bind(window);
  const repositoryBase = (() => {
    const first = window.location.pathname.split('/').filter(Boolean)[0];
    return first ? `/${first}/` : '/';
  })();

  function clean(value) {
    return String(value ?? '').trim();
  }

  function pathOf(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw, window.location.href).pathname;
    } catch (_) {
      return '';
    }
  }

  function methodOf(input, init) {
    return String(init?.method || input?.method || 'GET').toUpperCase();
  }

  function localizeAsset(node) {
    if (!(node instanceof Element)) return node;
    for (const attribute of ['src', 'href']) {
      const raw = node.getAttribute?.(attribute);
      if (!raw || !raw.startsWith('/') || raw.startsWith('//')) continue;
      if (raw.startsWith(repositoryBase)) continue;
      node.setAttribute(attribute, `${repositoryBase}${raw.slice(1)}`);
    }
    return node;
  }

  const nativeAppendChild = Node.prototype.appendChild;
  Node.prototype.appendChild = function appendChildPagesSafe(node) {
    return nativeAppendChild.call(this, localizeAsset(node));
  };

  const nativeInsertBefore = Node.prototype.insertBefore;
  Node.prototype.insertBefore = function insertBeforePagesSafe(node, reference) {
    return nativeInsertBefore.call(this, localizeAsset(node), reference);
  };

  if (Element.prototype.append) {
    const nativeAppend = Element.prototype.append;
    Element.prototype.append = function appendPagesSafe(...nodes) {
      return nativeAppend.apply(this, nodes.map(localizeAsset));
    };
  }

  if (!document.querySelector('link[rel="icon"]')) {
    const icon = document.createElement('link');
    icon.rel = 'icon';
    icon.href = 'data:,';
    nativeAppendChild.call(document.head, icon);
  }

  function value(row, name) {
    return clean(row.querySelector(`[name="${name}"]`)?.value);
  }

  function visibleSchedule(type) {
    const cards = [...document.querySelectorAll(`[data-schedule-card="${type}"]`)]
      .filter(card => card.isConnected && card.offsetParent !== null);
    const card = cards[cards.length - 1] || document.querySelector(`[data-schedule-card="${type}"]`);
    if (!card) return [];

    return [...card.querySelectorAll('tbody tr')].map((row, index) => {
      const namedActivity = value(row, 'activity');
      const namedStart = value(row, 'start_date');
      const namedEnd = value(row, 'end_date');
      const fields = [...row.querySelectorAll('input,select,textarea')];
      const positional = fields.map(field => clean(field.value));
      const activity = namedActivity || positional[type === 'thesis' ? 1 : 0] || '';
      const startDate = namedStart || positional[type === 'thesis' ? 2 : 1] || '';
      const endDate = namedEnd || positional[type === 'thesis' ? 3 : 2] || startDate;

      return {
        phase: type === 'thesis' ? (value(row, 'phase') || positional[0] || '') : '',
        activity,
        start_date: startDate,
        end_date: endDate,
        executed_date: value(row, 'executed_date'),
        execution_status: value(row, 'execution_status'),
        compliance_percentage: value(row, 'compliance_percentage'),
        evidence: value(row, 'evidence'),
        observation: value(row, 'observation'),
        sort_order: index + 1,
      };
    }).filter(item => item.activity && item.start_date && item.end_date);
  }

  async function bodyOf(input, init) {
    if (init?.body !== undefined && init?.body !== null) {
      if (typeof init.body === 'string') {
        try { return JSON.parse(init.body); } catch (_) { return {}; }
      }
      if (init.body instanceof URLSearchParams) {
        return Object.fromEntries(init.body.entries());
      }
    }
    if (input instanceof Request) {
      try { return await input.clone().json(); } catch (_) {}
    }
    return {};
  }

  window.fetch = async function githubPagesRuntimeFixesFetch(input, init) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    const match = path.match(/^\/api\/reports\/(\d+)\/schedules\/(complexive|thesis)$/);

    if (match && method === 'PUT') {
      const payload = await bodyOf(input, init);
      const fromDom = visibleSchedule(match[2]);
      const supplied = Array.isArray(payload.entries)
        ? payload.entries.filter(item => clean(item?.activity) && clean(item?.start_date) && clean(item?.end_date))
        : [];
      const entries = fromDom.length ? fromDom : supplied;

      if (!entries.length) {
        return new Response(JSON.stringify({
          ok: false,
          error: 'No se pudieron leer las actividades visibles del cronograma. Actualice la página y vuelva a intentarlo.',
        }), {
          status: 400,
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        });
      }

      const nextInit = {
        ...(init || {}),
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...((init && init.headers) || {}),
        },
        body: JSON.stringify({ ...payload, entries }),
      };
      return previousFetch(input, nextInit);
    }

    return previousFetch(input, init);
  };

  window.informtitGithubPagesFixes = Object.freeze({
    repositoryBase,
    visibleSchedule,
  });
})();
