import { maplibreGL } from "@maplibre/maplibre-gl-leaflet";
import { setWorkerUrl } from "maplibre-gl";

setWorkerUrl("/vendor/maplibre-gl-worker.mjs");
window.VietSafeVectorMaps = { maplibreGL };
