"""SPIRENS live-VM E2E harness — shared library.

Everything that talks to the VM or to Cloudflare funnels through this
package so the Claude Code permission surface stays tight. Phase modules
import helpers from here; they do not call subprocess, open sockets, or
read os.environ directly.
"""
