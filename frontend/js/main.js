/** VietSafe browser entrypoint: Leaflet is loaded locally before this module. */
import {removeOldWorkspace} from './views/map-ai.js';
import './views/app.js';
import {bindReportExport} from './views/export.js';
removeOldWorkspace();
bindReportExport();
