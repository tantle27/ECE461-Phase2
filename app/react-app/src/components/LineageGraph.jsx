import React, { useEffect, useRef, useState } from 'react'

// Dynamically import d3 so the dev server doesn't fail if d3 isn't installed yet.
export default function LineageGraph({ nodes = [], links = [] }) {
  const ref = useRef(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function render() {
      let d3
      try {
        d3 = await import('d3')
      } catch (err) {
        // d3 isn't available; show message in UI
        if (!cancelled) setMissing(true)
        return
      }

      if (cancelled) return

      const width = 600
      const height = 300
      const svg = d3.select(ref.current)
      svg.selectAll('*').remove()

      const sim = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(80))
        .force('charge', d3.forceManyBody().strength(-200))
        .force('center', d3.forceCenter(width / 2, height / 2))

      const link = svg.append('g')
        .attr('stroke', '#999')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('stroke-width', 1.5)

      const node = svg.append('g')
        .selectAll('circle')
        .data(nodes)
        .join('circle')
        .attr('r', 10)
        .attr('fill', '#3b82f6')
        .call(drag(sim, d3))

      const label = svg.append('g')
        .selectAll('text')
        .data(nodes)
        .join('text')
        .text(d => d.id)
        .attr('font-size', 10)
        .attr('dx', 12)
        .attr('dy', 4)

      sim.on('tick', () => {
        link
          .attr('x1', d => d.source.x)
          .attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x)
          .attr('y2', d => d.target.y)

        node.attr('cx', d => d.x).attr('cy', d => d.y)
        label.attr('x', d => d.x).attr('y', d => d.y)
      })

      // cleanup
      return () => sim.stop()
    }

    const cleanupPromise = render()

    return () => {
      cancelled = true
      // if render returned a cleanup function, call it
      if (cleanupPromise && typeof cleanupPromise.then === 'function') {
        cleanupPromise.then(fn => { if (typeof fn === 'function') fn() }).catch(() => {})
      }
    }
  }, [nodes, links])

  function drag(simulation, d3) {
    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
    }
    function dragged(event, d) {
      d.fx = event.x
      d.fy = event.y
    }
    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0)
      d.fx = null
      d.fy = null
    }
    return d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended)
  }

  if (missing) {
    return (
      <div className="p-4 bg-yellow-50 text-yellow-800 rounded">
        Lineage graph requires the <code>d3</code> package. Run <span className="font-mono">npm install</span> in the app folder and restart the dev server.
      </div>
    )
  }

  return (
    <svg ref={ref} width="100%" viewBox="0 0 600 300" role="img" aria-label="Artifact lineage graph"></svg>
  )
}
