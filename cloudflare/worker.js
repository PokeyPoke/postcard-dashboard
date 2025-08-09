/**
 * Cloudflare Worker for transit ETA data
 * Normalizes various transit APIs to a common format
 */

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

/**
 * Main request handler
 */
async function handleRequest(request) {
  const url = new URL(request.url)
  
  // Enable CORS for all origins
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  }

  // Handle preflight requests
  if (request.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders })
  }

  // Only handle GET requests to /v1/eta
  if (request.method !== 'GET' || !url.pathname.startsWith('/v1/eta')) {
    return new Response('Not Found', { 
      status: 404, 
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })
  }

  try {
    const etaData = await getTransitETA(url.searchParams)
    
    return new Response(JSON.stringify(etaData), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=30', // Cache for 30 seconds
      }
    })
  } catch (error) {
    console.error('Transit API error:', error)
    
    // Return a fallback response
    const fallback = generateFallbackETA(url.searchParams)
    return new Response(JSON.stringify(fallback), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
      }
    })
  }
}

/**
 * Get transit ETA data from upstream API or generate mock data
 */
async function getTransitETA(params) {
  const route = params.get('route') || 'N/A'
  const stop = params.get('stop') || 'N/A'
  
  // Check if we have an upstream transit API configured
  const upstreamUrl = TRANSIT_UPSTREAM || null
  
  if (upstreamUrl) {
    try {
      // Forward request to upstream API
      const upstreamResponse = await fetch(`${upstreamUrl}?${params.toString()}`, {
        headers: {
          'User-Agent': 'PostcardDashboard-Worker/1.0',
        },
        cf: {
          // Cache at edge for 30 seconds
          cacheTtl: 30,
          cacheEverything: true,
        }
      })
      
      if (upstreamResponse.ok) {
        const data = await upstreamResponse.json()
        // Normalize the response format
        return normalizeTransitResponse(data, route, stop)
      }
    } catch (error) {
      console.error('Upstream API error:', error)
    }
  }
  
  // Generate deterministic mock data based on route and time
  return generateMockETA(route, stop)
}

/**
 * Normalize different transit API responses to our standard format
 */
function normalizeTransitResponse(data, route, stop) {
  // If data is already in our format, return as-is
  if (data.route && data.hasOwnProperty('eta_s')) {
    return data
  }
  
  // Try to extract ETA from common formats
  let eta_s = null
  let status = 'Unknown'
  
  // Handle common API response formats
  if (data.predictions && data.predictions.length > 0) {
    // NextBus/TransLoc style
    const prediction = data.predictions[0]
    eta_s = prediction.seconds || prediction.minutes * 60 || null
    status = prediction.isDeparture ? 'Departing' : 'On Time'
  } else if (data.eta || data.eta_minutes) {
    // Simple ETA format
    eta_s = data.eta || data.eta_minutes * 60
    status = data.status || 'On Time'
  } else if (data.arrivals && data.arrivals.length > 0) {
    // GTFS Realtime style
    const arrival = data.arrivals[0]
    const now = Math.floor(Date.now() / 1000)
    eta_s = arrival.arrival_time - now
    status = arrival.schedule_relationship === 'CANCELED' ? 'Canceled' : 'On Time'
  }
  
  return {
    route: route,
    stop: stop,
    eta_s: eta_s,
    status: status,
    timestamp: Math.floor(Date.now() / 1000)
  }
}

/**
 * Generate deterministic mock ETA data for demonstration
 */
function generateMockETA(route, stop) {
  const now = new Date()
  const seed = `${route}-${stop}-${now.getHours()}-${Math.floor(now.getMinutes() / 5)}`
  
  // Simple hash function for deterministic randomness
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32-bit integer
  }
  
  const randomValue = Math.abs(hash) % 1000
  
  // Generate realistic ETA (1-15 minutes)
  const eta_minutes = 1 + (randomValue % 15)
  const eta_s = eta_minutes * 60
  
  // Determine status based on route and time
  const statuses = ['On Time', 'Delayed', 'Arriving']
  const statusIndex = Math.abs(hash) % statuses.length
  const status = statuses[statusIndex]
  
  return {
    route: route,
    stop: stop,
    eta_s: eta_s,
    status: status,
    timestamp: Math.floor(Date.now() / 1000),
    _mock: true
  }
}

/**
 * Generate fallback ETA when APIs fail
 */
function generateFallbackETA(params) {
  return {
    route: params.get('route') || 'N/A',
    stop: params.get('stop') || 'N/A',
    eta_s: null,
    status: 'Service Unavailable',
    timestamp: Math.floor(Date.now() / 1000),
    _fallback: true
  }
}

// Health check endpoint
addEventListener('fetch', event => {
  const url = new URL(event.request.url)
  
  if (url.pathname === '/health') {
    event.respondWith(new Response('OK', {
      headers: { 'Content-Type': 'text/plain' }
    }))
  }
})