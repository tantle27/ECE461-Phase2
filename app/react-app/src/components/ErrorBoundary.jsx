import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null, errorInfo: null, showDetails: false }
    this.handleRetry = this.handleRetry.bind(this)
    this.toggleDetails = this.toggleDetails.bind(this)
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo })
    // Optionally: log to remote monitoring here
  }

  handleRetry() {
    // Soft retry by clearing error state so children can re-render.
    this.setState({ error: null, errorInfo: null, showDetails: false })
  }

  toggleDetails() {
    this.setState((s) => ({ showDetails: !s.showDetails }))
  }

  render() {
    const { error, errorInfo, showDetails } = this.state
    if (error) {
      return (
        <div className="max-w-3xl mx-auto p-6 bg-white border rounded-md shadow-sm">
          <h2 className="text-xl font-semibold text-red-700">Something went wrong</h2>
          <p className="mt-2 text-sm text-gray-700">An unexpected error occurred while loading the page. You can try again or contact support if the problem persists.</p>

          <div className="mt-4 flex gap-2">
            <button onClick={this.handleRetry} className="px-3 py-1.5 bg-blue-600 text-white rounded-md">Try again</button>
            <button onClick={() => window.location.reload()} className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-md">Reload page</button>
            <button onClick={this.toggleDetails} className="px-3 py-1.5 bg-gray-50 border rounded-md">{showDetails ? 'Hide details' : 'Show details'}</button>
          </div>

          {showDetails && (
            <details className="mt-4 text-xs text-gray-600 whitespace-pre-wrap">
              <summary className="font-medium">Error details</summary>
              <div className="mt-2">
                <strong className="block text-sm text-red-600">{String(error && error.toString())}</strong>
                <div className="mt-2">{errorInfo && errorInfo.componentStack}</div>
              </div>
            </details>
          )}
        </div>
      )
    }

    return this.props.children
  }
}
