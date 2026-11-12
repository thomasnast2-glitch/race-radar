'use strict';

// Public reports describe source checks, not official registration availability.
const RadarStatus = {
  date(value) {
    if (!value || !/^\d{4}-\d{2}-\d{2}/.test(value)) return 'date inconnue';
    const date = new Date(value.length === 10 ? value + 'T12:00:00' : value);
    return Number.isNaN(date.getTime()) ? 'date inconnue' : date.toLocaleString('fr-FR', {
      timeZone: 'Europe/Paris', day: 'numeric', month: 'long', year: 'numeric',
      ...(value.length > 10 ? {hour: '2-digit', minute: '2-digit'} : {})
    });
  },
  summarize(kind, report, now = new Date()) {
    const rows = Array.isArray(report.sources) ? report.sources : [];
    const checked = report.last_checked || report.lastCheckedAt || report.checkedAt;
    const errors = kind === 'hyrox' ? (report.erreurs || []) : rows.filter(row =>
      kind === 'cycling' ? row.result !== 'OK' : !['links_found', 'ok'].includes(row.status));
    let text = kind === 'hyrox'
      ? `${report.flux_accessibles}/${report.flux_total} flux de presse accessibles · ${report.indices_conserves || 0} piste(s) à vérifier`
      : `${rows.length - errors.length}/${rows.length} source(s) accessible(s)`;
    const timestamp = checked && new Date(checked.length === 10 ? checked + 'T00:00:00Z' : checked).getTime();
    const stale = !Number.isFinite(timestamp) || now.getTime() - timestamp > 3 * 86400000;
    if (errors.length) text += ` · ${errors.length} erreur(s) de source`;
    if (stale) text += ' · contrôle ancien ou non daté';
    return {checked, text, warning: stale || errors.length > 0};
  },
  async json(url) {
    const response = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  },
  async loadReport(kind, file) {
    const element = document.getElementById('radar-' + kind);
    try {
      const report = this.summarize(kind, await this.json('./' + file));
      element.textContent = `Dernier contrôle : ${this.date(report.checked)}. ${report.text}.`;
      element.classList.toggle('radar-warning', report.warning);
    } catch {
      element.textContent = 'Rapport indisponible : consulter les exécutions GitHub ci-dessous.';
      element.classList.add('radar-warning');
    }
  },
  async loadActions() {
    const element = document.getElementById('radar-actions');
    try {
      const data = await this.json('https://api.github.com/repos/thomasnast2-glitch/race-radar/actions/runs?branch=main&per_page=40');
      const names = ['race-radar.yml', 'hyrox-radar.yml', 'cycling-radar.yml', 'ifttt-notifications.yml'];
      element.replaceChildren();
      for (const name of names) {
        const run = data.workflow_runs.find(run => run.path === '.github/workflows/' + name);
        const item = document.createElement('li');
        const label = {'race-radar.yml': 'Running', 'hyrox-radar.yml': 'HYROX', 'cycling-radar.yml': 'Cyclo', 'ifttt-notifications.yml': 'Notifications'}[name];
        const state = !run ? 'état indisponible' : run.status !== 'completed' ? 'en cours' :
          run.conclusion === 'success' ? 'réussie' : 'à vérifier (' + run.conclusion + ')';
        item.textContent = `${label} : ${state}${run ? ' · ' + this.date(run.updated_at) : ''}`;
        item.classList.toggle('radar-warning', !run || (run.status === 'completed' && run.conclusion !== 'success'));
        element.appendChild(item);
      }
    } catch {
      element.textContent = 'État des exécutions indisponible. Les rapports ci-dessus restent consultables ; ouvrir GitHub pour vérifier.';
    }
  },
  async load() {
    await Promise.allSettled([
      this.loadReport('running', 'source_watch.json'),
      this.loadReport('hyrox', 'hyrox_watch.json'),
      this.loadReport('cycling', 'cycling_watch.json'),
      this.loadActions()
    ]);
  }
};
if (typeof document !== 'undefined') RadarStatus.load();
