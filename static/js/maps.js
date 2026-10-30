/**
 * ShopFlow - Google Maps Delivery Location Module
 * Handles interactive map pin selection at checkout, address preview,
 * geolocation detection, and destination display on order tracking.
 */

// Global callback for Google Maps API script
window.initGoogleMapCallback = function () {
  if (typeof window.onGoogleMapsReady === 'function') {
    window.onGoogleMapsReady();
  }
};

// Global error handler for Google Maps authentication issues (invalid key / billing required)
window.gm_authFailure = function () {
  console.warn('Google Maps authentication failed (API key may be invalid, restricted, or billing not enabled). Activating fallback mode.');
  const checkoutMap = document.getElementById('checkoutMap');
  if (checkoutMap) {
    renderMapFallback(checkoutMap);
  }
  const orderMap = document.getElementById('orderMap');
  if (orderMap) {
    renderOrderMapFallback(orderMap);
  }
};

/**
 * Load Google Maps JavaScript API dynamically if API key is provided
 */
function loadGoogleMapsScript(apiKey, callback) {
  if (!apiKey || apiKey.trim() === '') {
    return false;
  }

  if (window.google && window.google.maps) {
    if (callback) callback();
    return true;
  }

  window.onGoogleMapsReady = callback;
  const script = document.createElement('script');
  script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&callback=initGoogleMapCallback`;
  script.async = true;
  script.defer = true;
  script.onerror = () => {
    console.warn('Failed to load Google Maps script. Switching to fallback mode.');
    window.gm_authFailure();
  };
  document.head.appendChild(script);
  return true;
}

/**
 * Render graceful fallback view on checkout page when no API key is provided or loading fails
 */
function renderMapFallback(container) {
  const latInput = document.getElementById('latitude');
  const lngInput = document.getElementById('longitude');
  const currentLat = latInput ? latInput.value : '';
  const currentLng = lngInput ? lngInput.value : '';

  container.innerHTML = `
    <div class="p-4 text-center d-flex flex-column align-items-center justify-content-center h-100 bg-light rounded-3 border">
      <div class="rounded-circle bg-primary-subtle text-primary p-3 mb-2 d-flex align-items-center justify-content-center" style="width: 56px; height: 56px;">
        <i class="bi bi-geo-alt-fill fs-3"></i>
      </div>
      <h6 class="fw-bold text-dark mb-1">Google Maps Delivery Location</h6>
      <p class="text-muted small mb-3" style="max-width: 420px;">
        Google Maps API key is not configured or in fallback mode. Your typed delivery address will be saved with your order. You can also detect GPS coordinates or preview the destination on Google Maps.
      </p>
      <div class="d-flex flex-wrap gap-2 justify-content-center">
        <a id="previewAddressMapsBtn" href="https://www.google.com/maps" target="_blank" class="btn btn-outline-primary btn-sm rounded-pill px-3">
          <i class="bi bi-box-arrow-up-right me-1"></i> Preview Address in Google Maps
        </a>
        <button type="button" class="btn btn-outline-secondary btn-sm rounded-pill px-3" onclick="document.getElementById('manualCoordsWrapper').classList.toggle('d-none')">
          <i class="bi bi-pin-map me-1"></i> Optional GPS Coordinates
        </button>
      </div>

      <div id="manualCoordsWrapper" class="mt-3 text-start w-100 p-2 bg-white rounded border ${currentLat ? '' : 'd-none'}" style="max-width: 440px;">
        <div class="row g-2 align-items-center small">
          <div class="col-6">
            <label class="form-label text-muted mb-0 small">Latitude:</label>
            <input type="number" step="any" class="form-control form-control-sm" id="manualLat" placeholder="e.g. 37.7749" value="${currentLat}" onchange="syncManualCoords()">
          </div>
          <div class="col-6">
            <label class="form-label text-muted mb-0 small">Longitude:</label>
            <input type="number" step="any" class="form-control form-control-sm" id="manualLng" placeholder="e.g. -122.4194" value="${currentLng}" onchange="syncManualCoords()">
          </div>
        </div>
      </div>
    </div>
  `;

  updatePreviewMapsUrl();
}

/**
 * Update the Google Maps external search URL based on typed address fields
 */
function updatePreviewMapsUrl() {
  const btn = document.getElementById('previewAddressMapsBtn');
  if (!btn) return;

  const addr = document.getElementById('shippingAddress')?.value.trim() || '';
  const city = document.getElementById('city')?.value.trim() || '';
  const zip = document.getElementById('postalCode')?.value.trim() || '';

  const fullAddr = [addr, city, zip].filter(Boolean).join(', ');
  if (fullAddr) {
    btn.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(fullAddr)}`;
  } else {
    btn.href = 'https://www.google.com/maps';
  }
}

/**
 * Sync manual coordinate inputs to form hidden inputs
 */
function syncManualCoords() {
  const manualLat = document.getElementById('manualLat');
  const manualLng = document.getElementById('manualLng');
  const latInput = document.getElementById('latitude');
  const lngInput = document.getElementById('longitude');

  if (manualLat && latInput) latInput.value = manualLat.value.trim();
  if (manualLng && lngInput) lngInput.value = manualLng.value.trim();

  updateCoordsBadge(manualLat ? manualLat.value : '', manualLng ? manualLng.value : '');
}

/**
 * Update the coordinates status badge on the checkout page
 */
function updateCoordsBadge(lat, lng) {
  const badge = document.getElementById('coordsBadge');
  const confirmedPill = document.getElementById('confirmedPill');

  if (lat && lng) {
    const latNum = parseFloat(lat).toFixed(4);
    const lngNum = parseFloat(lng).toFixed(4);
    if (badge) {
      badge.innerHTML = `<i class="bi bi-geo-alt-fill text-success me-1"></i> Destination Pin: <strong>${latNum}, ${lngNum}</strong>`;
      badge.classList.remove('d-none');
    }
    if (confirmedPill) {
      confirmedPill.classList.remove('d-none');
    }
  } else {
    if (badge) {
      badge.innerHTML = `<i class="bi bi-pin-map text-muted me-1"></i> Pin location not set (will use street address)`;
    }
    if (confirmedPill) {
      confirmedPill.classList.add('d-none');
    }
  }
}

/**
 * Initialize Checkout Delivery Map
 */
function setupCheckoutDeliveryMap(apiKey) {
  const mapContainer = document.getElementById('checkoutMap');
  if (!mapContainer) return;

  // Listen to address input changes to keep fallback Google Maps preview link fresh
  ['shippingAddress', 'city', 'postalCode'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', updatePreviewMapsUrl);
    }
  });

  // Setup "Detect My Location" button (HTML5 Geolocation)
  const detectBtn = document.getElementById('btnDetectLocation');
  if (detectBtn) {
    detectBtn.addEventListener('click', () => {
      if (!navigator.geolocation) {
        showToast('Geolocation is not supported by your browser.', 'warning');
        return;
      }

      detectBtn.disabled = true;
      detectBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Locating...';

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          detectBtn.disabled = false;
          detectBtn.innerHTML = '<i class="bi bi-crosshair me-1"></i> Detect My Location';

          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;

          const latInput = document.getElementById('latitude');
          const lngInput = document.getElementById('longitude');
          if (latInput) latInput.value = lat;
          if (lngInput) lngInput.value = lng;

          const manualLat = document.getElementById('manualLat');
          const manualLng = document.getElementById('manualLng');
          if (manualLat) manualLat.value = lat;
          if (manualLng) manualLng.value = lng;

          updateCoordsBadge(lat, lng);

          // If Google Maps instance exists, move marker & center
          if (window.checkoutMapInstance && window.checkoutMarkerInstance) {
            const newPos = { lat, lng };
            window.checkoutMapInstance.setCenter(newPos);
            window.checkoutMapInstance.setZoom(15);
            window.checkoutMarkerInstance.setPosition(newPos);
          }

          showToast('Current location detected and destination pin set!', 'success');
        },
        (err) => {
          detectBtn.disabled = false;
          detectBtn.innerHTML = '<i class="bi bi-crosshair me-1"></i> Detect My Location';
          console.warn('Geolocation error:', err.message);
          showToast(`Location access: ${err.message}. You can enter coordinates manually or pin on map.`, 'info');
        },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    });
  }

  // Setup "Confirm Location" button
  const confirmBtn = document.getElementById('btnConfirmLocation');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', () => {
      const lat = document.getElementById('latitude')?.value;
      const lng = document.getElementById('longitude')?.value;
      if (lat && lng) {
        updateCoordsBadge(lat, lng);
        showToast(`Delivery location confirmed at Lat: ${parseFloat(lat).toFixed(4)}, Lng: ${parseFloat(lng).toFixed(4)}`, 'success');
      } else {
        showToast('Please click on the map or click "Detect My Location" first to set a delivery pin.', 'warning');
      }
    });
  }

  // Attempt to load Google Maps script if API key is provided
  const scriptLoaded = loadGoogleMapsScript(apiKey, () => {
    initInteractiveGoogleMap(mapContainer);
  });

  if (!scriptLoaded) {
    renderMapFallback(mapContainer);
  }
}

/**
 * Initialize interactive Google Maps instance
 */
function initInteractiveGoogleMap(container) {
  try {
    const latInput = document.getElementById('latitude');
    const lngInput = document.getElementById('longitude');

    // Default position (San Francisco or previously saved)
    let initialLat = latInput && latInput.value ? parseFloat(latInput.value) : 37.7749;
    let initialLng = lngInput && lngInput.value ? parseFloat(lngInput.value) : -122.4194;
    const initialPos = { lat: initialLat, lng: initialLng };

    const map = new google.maps.Map(container, {
      zoom: 13,
      center: initialPos,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true
    });
    window.checkoutMapInstance = map;

    const marker = new google.maps.Marker({
      position: initialPos,
      map: map,
      draggable: true,
      title: 'Delivery Destination (Drag to adjust)',
      animation: google.maps.Animation.DROP
    });
    window.checkoutMarkerInstance = marker;

    function onPositionChanged(pos) {
      const lat = pos.lat();
      const lng = pos.lng();
      if (latInput) latInput.value = lat;
      if (lngInput) lngInput.value = lng;

      const manualLat = document.getElementById('manualLat');
      const manualLng = document.getElementById('manualLng');
      if (manualLat) manualLat.value = lat;
      if (manualLng) manualLng.value = lng;

      updateCoordsBadge(lat, lng);
    }

    // Map Click Listener
    map.addListener('click', (e) => {
      marker.setPosition(e.latLng);
      onPositionChanged(e.latLng);
      showToast('Delivery pin updated to clicked map position.', 'info');
    });

    // Marker Drag Listener
    marker.addListener('dragend', () => {
      onPositionChanged(marker.getPosition());
      showToast('Delivery pin repositioned.', 'info');
    });

    // Setup Geocode Address Button
    const geocodeBtn = document.getElementById('btnGeocodeAddress');
    if (geocodeBtn) {
      geocodeBtn.addEventListener('click', () => {
        const addr = document.getElementById('shippingAddress')?.value.trim() || '';
        const city = document.getElementById('city')?.value.trim() || '';
        const zip = document.getElementById('postalCode')?.value.trim() || '';
        const fullAddr = [addr, city, zip].filter(Boolean).join(', ');

        if (!fullAddr) {
          showToast('Please type your street address first.', 'warning');
          return;
        }

        const geocoder = new google.maps.Geocoder();
        geocoder.geocode({ address: fullAddr }, (results, status) => {
          if (status === 'OK' && results[0]) {
            const loc = results[0].geometry.location;
            map.setCenter(loc);
            map.setZoom(15);
            marker.setPosition(loc);
            onPositionChanged(loc);
            showToast(`Pin centered on: ${results[0].formatted_address}`, 'success');
          } else {
            showToast('Could not geocode this address. You can click on the map to place the pin manually.', 'warning');
          }
        });
      });
    }

  } catch (e) {
    console.error('Error initializing Google Maps:', e);
    renderMapFallback(container);
  }
}

/**
 * Render graceful fallback on Order Details and Admin pages
 */
function renderOrderMapFallback(container) {
  const lat = container.dataset.lat;
  const lng = container.dataset.lng;
  const address = container.dataset.address || '';
  const googleMapsUrl = container.dataset.mapsUrl || 'https://www.google.com/maps';

  container.innerHTML = `
    <div class="p-3 text-center d-flex flex-column align-items-center justify-content-center h-100 bg-light rounded-3 border">
      <i class="bi bi-geo-alt-fill fs-2 text-primary mb-2"></i>
      <div class="fw-bold text-dark small mb-1">Destination Location</div>
      <div class="text-muted small mb-2" style="font-size: 0.8rem;">
        ${lat && lng ? `Coordinates: <strong>${parseFloat(lat).toFixed(4)}, ${parseFloat(lng).toFixed(4)}</strong>` : address}
      </div>
      <a href="${googleMapsUrl}" target="_blank" class="btn btn-outline-primary btn-sm rounded-pill px-3">
        <i class="bi bi-box-arrow-up-right me-1"></i> Open in Google Maps
      </a>
    </div>
  `;
}

/**
 * Initialize Destination Map on Order Details and Admin Order Inspection pages
 */
function setupOrderDestinationMap(apiKey) {
  const container = document.getElementById('orderMap');
  if (!container) return;

  const latStr = container.dataset.lat;
  const lngStr = container.dataset.lng;
  const address = container.dataset.address || '';

  if (!apiKey || apiKey.trim() === '') {
    renderOrderMapFallback(container);
    return;
  }

  const scriptLoaded = loadGoogleMapsScript(apiKey, () => {
    try {
      let lat = latStr ? parseFloat(latStr) : null;
      let lng = lngStr ? parseFloat(lngStr) : null;

      if (lat !== null && lng !== null) {
        const pos = { lat, lng };
        const map = new google.maps.Map(container, {
          zoom: 14,
          center: pos,
          mapTypeControl: false,
          streetViewControl: false
        });
        new google.maps.Marker({
          position: pos,
          map: map,
          title: 'Confirmed Delivery Destination'
        });
      } else if (address) {
        // Geocode destination by address
        const geocoder = new google.maps.Geocoder();
        geocoder.geocode({ address }, (results, status) => {
          if (status === 'OK' && results[0]) {
            const loc = results[0].geometry.location;
            const map = new google.maps.Map(container, {
              zoom: 14,
              center: loc,
              mapTypeControl: false,
              streetViewControl: false
            });
            new google.maps.Marker({
              position: loc,
              map: map,
              title: address
            });
          } else {
            renderOrderMapFallback(container);
          }
        });
      } else {
        renderOrderMapFallback(container);
      }
    } catch (e) {
      console.warn('Error loading order destination map:', e);
      renderOrderMapFallback(container);
    }
  });

  if (!scriptLoaded) {
    renderOrderMapFallback(container);
  }
}
