(() => {
  'use strict';

  if (typeof window === 'undefined' || !/(^|\.)github\.io$/i.test(window.location.hostname)) return;

  const VERSION = '1.1.0';
  const MARKER = 'INDEPENDENT_COMPONENT_VALIDATION_V1';
  const previousFetch = window.fetch.bind(window);
  const clean = value => String(value ?? '').replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ');
  const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  const pathOf = input => {
    try { return new URL(typeof input === 'string' ? input : input?.url, window.location.href).pathname; }
    catch (_) { return ''; }
  };
  const methodOf = (input, init) => String(init?.method || input?.method || 'GET').toUpperCase();
  const jsonResponse = (payload, status = 200) => Promise.resolve(new Response(JSON.stringify(payload), { status, headers:{'Content-Type':'application/json; charset=utf-8'} }));

  function periodIdOf(report = {}) {
    return clean(report.periodoId || report.firebase_period_id || report.period_id || report.periodId);
  }

  async function fetchJson(path) {
    const response = await previousFetch(path, { method:'GET', cache:'no-store' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || `Error ${response.status}`);
    return payload;
  }

  async function rawComplexive(periodId) {
    if (!periodId) return [];
    if (!window.InformtitNeon?.getClient) throw new Error('Neon no está disponible.');
    const db = await window.InformtitNeon.getClient();
    const result = await db.from('complexive_results')
      .select('student_id,theoretical_grade,practical_grade,accumulated_grade,supplementary_theoretical,supplementary_practical,final_grade,final_status')
      .eq('period_id', periodId);
    if (result?.error) throw result.error;
    return Array.isArray(result?.data) ? result.data : [];
  }

  async function sourceHealth(report = {}) {
    const periodId = periodIdOf(report);
    if (!periodId) return { periodId, statuses:[], errors:[{ source:'Período', error:'No existe periodId.', critical:true }] };
    const neon = window.InformtitNeon;
    if (!neon) return { periodId, statuses:[], errors:[{ source:'Neon PostgreSQL', error:'La API Neon no está disponible.', critical:true }] };

    const checks = [
      ['Estudiantes', true, () => neon.estudiantes()],
      ['Matrículas', true, () => neon.matriculas(periodId)],
      ['Requisitos', true, () => neon.requisitos(periodId)],
      ['Cronogramas', false, () => neon.schedules(periodId)],
      ['Núcleos', false, () => neon.nucleos(periodId)],
      ['Examen Complexivo', false, () => neon.complexivo(periodId)],
      ['Trabajo de Titulación', false, () => neon.trabajoTitulacion(periodId)],
    ];
    const statuses = await Promise.all(checks.map(async ([source, critical, fn]) => {
      try { await fn(); return { source, critical, ok:true, error:'' }; }
      catch (error) { return { source, critical, ok:false, error:clean(error?.message || error) || 'No respondió.' }; }
    }));
    return { periodId, statuses, errors:statuses.filter(item => !item.ok) };
  }

  function statusFor(health, source) {
    return (health?.statuses || []).find(item => item.source === source) || { source, ok:true, error:'', critical:false };
  }

  async function reportBundle(reportId) {
    const [reportData, roster, nuclei, projects, schedules] = await Promise.all([
      fetchJson(`/api/reports/${reportId}`),
      fetchJson(`/api/reports/${reportId}/roster`),
      fetchJson(`/api/reports/${reportId}/nuclei`),
      fetchJson(`/api/reports/${reportId}/projects`),
      fetchJson(`/api/reports/${reportId}/schedules`).catch(error => ({ ok:false, error:clean(error?.message || error), schedules:{complexive:[],thesis:[]} })),
    ]);
    return {
      report: reportData.report || {},
      roster: roster || {},
      nuclei: nuclei || {},
      projects: projects || {},
      schedules: schedules || {},
    };
  }

  function buildAudit(bundle, health, outputLabel = '', complexiveRows = []) {
    const report = bundle.report || {};
    const students = Array.isArray(bundle.roster?.students) ? bundle.roster.students : [];
    const courses = Array.isArray(bundle.nuclei?.courses) ? bundle.nuclei.courses : [];
    const projects = Array.isArray(bundle.projects?.projects) ? bundle.projects.projects : [];
    const schedules = bundle.schedules?.schedules || { complexive:[], thesis:[] };
    const periodId = periodIdOf(report) || health?.periodId || '';
    const controls = [];
    const push = (name, status, detail, component = '') => controls.push({ name, status, detail, component });

    push('Período académico', periodId ? 'ok' : 'error', periodId ? `${report.period || periodId} · ${periodId}` : 'No existe período activo.', 'core');
    push('Datos generales', report.name && report.period ? 'ok' : 'error', report.name && report.period ? 'Nombre y período identificados.' : 'Faltan nombre o período.', 'core');

    const reqHealth = statusFor(health, 'Requisitos');
    const blankStudents = students.filter(row => Array.isArray(row.blank_requirements) && row.blank_requirements.length).length;
    const noCumpleStudents = students.filter(row => Array.isArray(row.pending_requirements) && row.pending_requirements.length).length;
    if (!reqHealth.ok) push('Requisitos', 'error', reqHealth.error, 'requirements');
    else if (!students.length) push('Requisitos', 'empty', 'No existen estudiantes cargados.', 'requirements');
    else if (blankStudents) push('Requisitos', 'warning', `${blankStudents} estudiantes tienen datos de requisitos faltantes. ${noCumpleStudents} tienen uno o más NO CUMPLE.`, 'requirements');
    else push('Requisitos', 'ok', `${students.length} estudiantes · ${students.length - noCumpleStudents} sin NO CUMPLE · ${noCumpleStudents} con uno o más NO CUMPLE. Los NO CUMPLE son un resultado válido, no un error de fuente.`, 'requirements');

    const undefinedRoutes = students.filter(row => row.route === 'SIN_DEFINIR' || row.route === 'UNDEFINED' || !clean(row.route)).length;
    push('Rutas de titulación', undefinedRoutes ? 'warning' : 'ok', undefinedRoutes ? `${undefinedRoutes} estudiantes todavía no tienen ruta confirmada. Las cargas de Núcleos, Complexivo o Trabajo de Titulación irán resolviendo la ruta por cédula.` : 'Las rutas de titulación de la población están definidas.', 'routes');

    const scheduleHealth = statusFor(health, 'Cronogramas');
    if (!scheduleHealth.ok) {
      push('Cronograma Núcleos / Complexivo', 'error', scheduleHealth.error, 'schedule_complexive');
      push('Cronograma Trabajo de Titulación', 'error', scheduleHealth.error, 'schedule_thesis');
    } else {
      const complexiveScheduleCount = Array.isArray(schedules.complexive) ? schedules.complexive.length : 0;
      const thesisScheduleCount = Array.isArray(schedules.thesis) ? schedules.thesis.length : 0;
      push('Cronograma Núcleos / Complexivo', complexiveScheduleCount ? 'ok' : 'warning', complexiveScheduleCount ? `${complexiveScheduleCount} actividades registradas.` : 'Cronograma todavía sin actividades.', 'schedule_complexive');
      push('Cronograma Trabajo de Titulación', thesisScheduleCount ? 'ok' : 'warning', thesisScheduleCount ? `${thesisScheduleCount} actividades registradas.` : 'Cronograma todavía sin actividades.', 'schedule_thesis');
    }

    const nucleiHealth = statusFor(health, 'Núcleos');
    const expectedComplexive = students.filter(row => row.route === 'COMPLEXIVO').length;
    const withNuclei = students.filter(row => row.route === 'COMPLEXIVO' && row.has_nuclei).length;
    if (!nucleiHealth.ok) push('Núcleos', 'error', nucleiHealth.error, 'nuclei');
    else if (!courses.length) push('Núcleos', expectedComplexive ? 'warning' : 'empty', expectedComplexive ? `${expectedComplexive} estudiantes de Complexivo esperan Núcleos.` : 'Sin registros de Núcleos. Este componente permanece independiente.', 'nuclei');
    else push('Núcleos', expectedComplexive && withNuclei < expectedComplexive ? 'warning' : 'ok', `${courses.length} cursos/núcleos · ${withNuclei} de ${expectedComplexive || withNuclei} estudiantes con evidencia de Núcleos.`, 'nuclei');

    const complexHealth = statusFor(health, 'Examen Complexivo');
    const ordinary = complexiveRows.filter(row => finite(row.theoretical_grade) || finite(row.practical_grade) || finite(row.accumulated_grade));
    const supplementary = complexiveRows.filter(row => finite(row.supplementary_theoretical) || finite(row.supplementary_practical));
    if (!complexHealth.ok) {
      push('Examen Complexivo ordinario', 'error', complexHealth.error, 'complexive_ordinary');
      push('Examen Complexivo supletorio', 'error', complexHealth.error, 'complexive_supplementary');
    } else {
      push('Examen Complexivo ordinario', ordinary.length ? 'ok' : (expectedComplexive ? 'warning' : 'empty'), ordinary.length ? `${ordinary.length} resultados ordinarios registrados.` : 'Sin resultados ordinarios.', 'complexive_ordinary');
      push('Examen Complexivo supletorio', supplementary.length ? 'ok' : 'empty', supplementary.length ? `${supplementary.length} resultados supletorios registrados.` : 'Sin resultados supletorios. Esto no invalida el ordinario.', 'complexive_supplementary');
    }

    const thesisHealth = statusFor(health, 'Trabajo de Titulación');
    const expectedThesis = students.filter(row => row.route === 'TRABAJO_TITULACION').length;
    if (!thesisHealth.ok) push('Trabajo de Titulación', 'error', thesisHealth.error, 'thesis');
    else if (!projects.length) push('Trabajo de Titulación', expectedThesis ? 'warning' : 'empty', expectedThesis ? `${expectedThesis} estudiantes están en esta ruta y aún no tienen registro.` : 'Sin estudiantes en Trabajo de Titulación.', 'thesis');
    else push('Trabajo de Titulación', expectedThesis && projects.length < expectedThesis ? 'warning' : 'ok', `${projects.length} estudiantes con registro.`, 'thesis');

    const criticalHealthErrors = (health?.errors || []).filter(item => item.critical);
    const coreBlocking = criticalHealthErrors.length > 0 || controls.some(item => item.component === 'core' && item.status === 'error');
    const componentErrors = controls.filter(item => item.status === 'error' && item.component !== 'core');
    const warnings = controls.filter(item => item.status === 'warning');
    const finalReady = !coreBlocking && !componentErrors.length && !warnings.length;
    const state = coreBlocking ? 'ERROR DE FUENTE' : (componentErrors.length || warnings.length ? 'REVISAR COMPONENTES' : 'APTO PARA EMITIR');

    return {
      document_title: report.name || 'Informe Final de Titulación',
      output_label: clean(outputLabel),
      state,
      controls,
      can_generate_pdf: !coreBlocking,
      final_ready: finalReady,
      mode: students.length ? 'normal' : 'no_population',
      independent_components: true,
      component_summary: {
        requirements: controls.find(item => item.component === 'requirements')?.status || 'empty',
        routes: controls.find(item => item.component === 'routes')?.status || 'warning',
        nuclei: controls.find(item => item.component === 'nuclei')?.status || 'empty',
        complexive_ordinary: controls.find(item => item.component === 'complexive_ordinary')?.status || 'empty',
        complexive_supplementary: controls.find(item => item.component === 'complexive_supplementary')?.status || 'empty',
        thesis: controls.find(item => item.component === 'thesis')?.status || 'empty',
        schedule_complexive: controls.find(item => item.component === 'schedule_complexive')?.status || 'empty',
        schedule_thesis: controls.find(item => item.component === 'schedule_thesis')?.status || 'empty',
      },
      reconciliation_label: 'Validación independiente por componente',
      reconciliation: { imported:courses.reduce((sum, course) => sum + (course.students?.length || 0), 0), included:withNuclei, excluded:0, reasons:{} },
      nuclei_population: {
        expected_students: expectedComplexive,
        with_nuclei: withNuclei,
        missing_students: Math.max(0, expectedComplexive - withNuclei),
        coverage: expectedComplexive ? (withNuclei * 100) / expectedComplexive : null,
        missing: students.filter(row => row.route === 'COMPLEXIVO' && !row.has_nuclei).slice(0,25).map(row => ({ full_name:row.full_name, career_name:row.career_name })),
      },
      traceability: {
        source:'NEON_POSTGRESQL',
        period_id:periodId,
        students:students.length,
        routes_undefined:undefinedRoutes,
        requirements_missing:blankStudents,
        requirements_no_cumple:noCumpleStudents,
        ordinary_results:ordinary.length,
        supplementary_results:supplementary.length,
        thesis_results:projects.length,
        source_errors:(health?.errors || []).map(item => `${item.source}: ${item.error}`),
      },
    };
  }

  const priorStability = window.InformtitPagesStability || {};
  window.InformtitPagesStability = Object.freeze({
    ...priorStability,
    sourceHealth,
    buildAudit,
    version: VERSION,
    standard:'SVD_2_1_INDEPENDENT',
  });

  window.fetch = async function independentValidationFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    const match = path.match(/^\/api\/reports\/(\d+)\/audit$/);
    if (match && method === 'GET') {
      try {
        const reportId = Number(match[1]);
        const bundle = await reportBundle(reportId);
        const health = await sourceHealth(bundle.report);
        const complexiveRows = await rawComplexive(periodIdOf(bundle.report) || health.periodId);
        const audit = buildAudit(bundle, health, '', complexiveRows);
        return jsonResponse({ ok:true, audit, preflight_token:`independent-${Date.now()}` });
      } catch (error) {
        return jsonResponse({ ok:false, error:clean(error?.message || error) || 'No se pudo validar el período.' }, 500);
      }
    }
    return previousFetch(input, init);
  };

  window.InformtitIndependentValidation = Object.freeze({ VERSION, MARKER, sourceHealth, buildAudit, rawComplexive });
})();