// Light in dark water, computed live. Four colours of ink are let into still black water, a little at a time,
// and the water (a small incompressible fluid solver) curls each one into plumes and threads before it fades.
//
// The ink is stored as light, so where two colours cross they add up toward white instead of turning to mud,
// and the picture is mostly darkness: each colour is only ever a guest in it. Colours take turns in a shuffled
// order and land at unrelated places, so none of them owns a corner of the screen.
(function () {
  'use strict';
  var canvas = document.getElementById('ink');
  if (!canvas) return;
  var root = document.documentElement;
  var query = new URLSearchParams(location.search);
  var still = query.has('still') || matchMedia('(prefers-reduced-motion: reduce)').matches;
  var gl = canvas.getContext('webgl2', { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: 'high-performance' });
  if (!gl || !(gl.getExtension('EXT_color_buffer_float') || gl.getExtension('EXT_color_buffer_half_float'))) {
    root.classList.add('no-ink'); // the stylesheet shows a still glow instead
    return;
  }

  var TURN = 6.283185307;
  function lin(r, g, b) { return [Math.pow(r, 2.2), Math.pow(g, 2.2), Math.pow(b, 2.2)]; }
  var COLOURS = [lin(0.259, 0.522, 0.957), lin(0.204, 0.659, 0.325), lin(0.984, 0.737, 0.02), lin(0.918, 0.263, 0.208)];
  var GAIN = [1.25, 1.2, 0.95, 1.2];   // so the four read as equally bright: yellow is the lightest of them
  var MARGIN = 0.09;                  // the water is a little larger than the window, so its edges are never seen

  var VERT = '#version 300 es\nprecision highp float;layout(location=0) in vec2 aPos;out vec2 vUv;' +
    'void main(){vUv=aPos*0.5+0.5;gl_Position=vec4(aPos,0.,1.);}';
  var HEAD = '#version 300 es\nprecision highp float;precision highp sampler2D;in vec2 vUv;out vec4 o;';
  var NOISE = 'float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}' +
    'float vnoise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);' +
    'return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}' +
    'float fbm(vec2 p){float a=.5,s=0.;for(int i=0;i<4;i++){s+=a*vnoise(p);p=p*2.03+17.1;a*=.5;}return s;}';
  var AROUND = 'float L=texture(uF,vUv-vec2(uTexel.x,0)).C,R=texture(uF,vUv+vec2(uTexel.x,0)).C,' +
    'B=texture(uF,vUv-vec2(0,uTexel.y)).C,T=texture(uF,vUv+vec2(0,uTexel.y)).C;';

  // 1 on the line of type, falling to 0 a little way off it. Takes a place in the window (0..1 both ways).
  var NEAR = 'uniform vec2 uLine,uLineHalf;uniform float uAspect;' +
    'float near(vec2 w,float reach){vec2 a=max(abs(w-uLine)-uLineHalf,0.);a.x*=uAspect;return 1.-smoothstep(0.,reach,length(a));}';

  var SRC = {
    // whatever is in the water goes where the water goes, and thins as it travels
    // Light that drifts onto the line of type goes out sooner, so the type keeps a clearing round it. And the
    // faintest light goes out first (uFade), so an old plume thins to threads and is gone, instead of
    // hanging about as a dull haze.
    carry: HEAD + NEAR + 'uniform sampler2D uVel,uSrc;uniform vec2 uTexel;uniform float uDt,uKeep,uClear,uFade,uMargin;' +
      'void main(){float n=near((vUv-uMargin)/(1.-2.*uMargin),.3);float k=uKeep*exp(-uClear*n*n);' +
      'vec4 v=k*textureLod(uSrc,vUv-uDt*texture(uVel,vUv).xy*uTexel,0.);' +
      'o=uFade>0.?v*max(0.,1.-uFade/(dot(v.rgb,vec3(.2126,.7152,.0722))+1e-3)):v;}',
    add: HEAD + 'uniform sampler2D uTarget;uniform vec2 uPoint;uniform vec4 uValue;uniform float uAspect,uRadius;' +
      'void main(){vec2 p=vUv-uPoint;p.x*=uAspect;o=textureLod(uTarget,vUv,0.)+exp(-dot(p,p)/uRadius)*uValue;}',
    // the drift of the water: the curl of a slow noise field, so it never piles up anywhere
    stir: HEAD + NOISE + 'uniform sampler2D uVel;uniform float uTime,uAmp,uAspect;' +
      'float psi(vec2 p){return fbm(p*1.1+vec2(uTime*.017,-uTime*.013))+.4*fbm(p*2.6-vec2(uTime*.011,uTime*.015));}' +
      'void main(){vec2 p=vec2(vUv.x*uAspect,vUv.y);float e=.012;' +
      'vec2 c=vec2(psi(p+vec2(0,e))-psi(p-vec2(0,e)),-(psi(p+vec2(e,0))-psi(p-vec2(e,0))))/(2.*e);' +
      'o=vec4(texture(uVel,vUv).xy+uAmp*c,0.,1.);}',
    // how much the water is turning at each point, and a push that keeps its small eddies from smearing away
    curl: HEAD + 'uniform sampler2D uVel;uniform vec2 uTexel;' +
      'void main(){float L=texture(uVel,vUv-vec2(uTexel.x,0)).y,R=texture(uVel,vUv+vec2(uTexel.x,0)).y,' +
      'B=texture(uVel,vUv-vec2(0,uTexel.y)).x,T=texture(uVel,vUv+vec2(0,uTexel.y)).x;o=vec4(.5*(R-L-T+B),0,0,1);}',
    eddy: HEAD + 'uniform sampler2D uVel,uF;uniform vec2 uTexel;uniform float uStrength,uDt;' +
      'void main(){' + AROUND.replace(/\.C/g, '.x') + 'float c=texture(uF,vUv).x;' +
      'vec2 f=.5*vec2(abs(T)-abs(B),abs(R)-abs(L));f/=length(f)+1e-4;f*=uStrength*c;f.y*=-1.;' +
      'o=vec4(texture(uVel,vUv).xy+f*uDt,0.,1.);}',
    divergence: HEAD + 'uniform sampler2D uVel;uniform vec2 uTexel;' +
      'void main(){float L=texture(uVel,vUv-vec2(uTexel.x,0)).x,R=texture(uVel,vUv+vec2(uTexel.x,0)).x,' +
      'B=texture(uVel,vUv-vec2(0,uTexel.y)).y,T=texture(uVel,vUv+vec2(0,uTexel.y)).y;o=vec4(.5*(R-L+T-B),0,0,1);}',
    pressure: HEAD + 'uniform sampler2D uF,uDiv;uniform vec2 uTexel;' +
      'void main(){' + AROUND.replace(/\.C/g, '.x') + 'o=vec4((L+R+B+T-texture(uDiv,vUv).x)*.25,0,0,1);}',
    project: HEAD + 'uniform sampler2D uF,uVel;uniform vec2 uTexel;' +
      'void main(){' + AROUND.replace(/\.C/g, '.x') + 'o=vec4(texture(uVel,vUv).xy-vec2(R-L,T-B),0.,1.);}',
    probe: HEAD + 'uniform sampler2D uDye;void main(){o=vec4(vec3(clamp(dot(textureLod(uDye,vUv,3.).rgb,vec3(.2126,.7152,.0722))*.7,0.,1.)),1.);}',
    // The ink itself, plus wider and wider blurs of it for the glow round each plume. The blurs are read
    // through a smooth curve, or their coarse grid would show as squares. On the line of type the light is
    // held down, so the type always sits on something dark enough to read against.
    show: HEAD + NEAR + 'uniform sampler2D uDye;uniform float uMargin;' +
      'vec4 cubic(float v){vec4 n=vec4(1.,2.,3.,4.)-v;vec4 s=n*n*n;float x=s.x,y=s.y-4.*s.x,z=s.z-4.*s.y+6.*s.x;return vec4(x,y,z,6.-x-y-z)/6.;}' +
      'vec3 wide(vec2 uv,int lod){vec2 size=vec2(textureSize(uDye,lod));vec2 p=uv*size-.5;vec2 f=fract(p);p-=f;' +
      'vec4 xc=cubic(f.x),yc=cubic(f.y);vec4 c=p.xxyy+vec2(-.5,1.5).xyxy;vec4 s=vec4(xc.xz+xc.yw,yc.xz+yc.yw);' +
      'vec4 at=(c+vec4(xc.yw,yc.yw)/s)/size.xxyy;float l=float(lod);' +
      'vec3 a=textureLod(uDye,at.xz,l).rgb,b=textureLod(uDye,at.yz,l).rgb,d=textureLod(uDye,at.xw,l).rgb,e=textureLod(uDye,at.yw,l).rgb;' +
      'float sx=s.x/(s.x+s.y),sy=s.z/(s.z+s.w);return mix(mix(e,d,sx),mix(b,a,sx),sy);}' +
      'void main(){vec2 uv=uMargin+(1.-2.*uMargin)*vUv;' +
      'vec3 light=textureLod(uDye,uv,0.).rgb*.5+wide(uv,1)*.3+wide(uv,3)*.4+wide(uv,5)*.55+wide(uv,7)*.5;' +
      'vec3 c=1.-exp(-light*1.3);' +
      'float lum=dot(c,vec3(.2126,.7152,.0722)),cap=exp(mix(log(2.),log(.085),near(vUv,.1)));' +
      'c*=cap*(1.-exp(-lum/cap))/max(lum,1e-4);' +
      'vec2 q=vec2((vUv.x-.5)*uAspect,vUv.y-.5);' +
      'c*=1.-.2*dot(q,q);' +
      'c+=vec3(.00026,.00049,.00143);' +
      'float n=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-.5;' +
      'o=vec4(pow(max(c,0.),vec3(1./2.2))+n*2.4/255.,1.);}'
  };

  function compile(type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  var P = {};
  try {
    var vert = compile(gl.VERTEX_SHADER, VERT);
    Object.keys(SRC).forEach(function (name) {
      var p = gl.createProgram();
      gl.attachShader(p, vert);
      gl.attachShader(p, compile(gl.FRAGMENT_SHADER, SRC[name]));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
      var u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (var i = 0; i < n; i++) { var info = gl.getActiveUniform(p, i); u[info.name] = gl.getUniformLocation(p, info.name); }
      P[name] = { program: p, u: u };
    });
  } catch (err) {
    root.classList.add('no-ink');
    if (window.console) console.warn('ink: ' + err.message);
    return;
  }

  gl.bindVertexArray(gl.createVertexArray());
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

  function target(w, h, internal, blurs) {       // blurs: keep smaller copies of it too, for the glow
    var t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, blurs ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texStorage2D(gl.TEXTURE_2D, blurs ? Math.floor(Math.log2(Math.max(w, h))) + 1 : 1, internal, w, h);
    var fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    return { tex: t, fbo: fbo, w: w, h: h };
  }
  function pair(w, h, internal, blurs) {
    var a = target(w, h, internal, blurs), b = target(w, h, internal, blurs);
    return { get read() { return a; }, get write() { return b; }, swap: function () { var t = a; a = b; b = t; } };
  }
  function free(t) { if (t) { gl.deleteTexture(t.tex); gl.deleteFramebuffer(t.fbo); } }
  function freePair(p) { if (p) { free(p.read); free(p.write); } }

  var PROBE_W = 40, PROBE_H = 24, seen = new Uint8Array(PROBE_W * PROBE_H * 4), probe = null;
  var vel, dye, pressure, div, curl, aspect = 1, simTexel, dyeTexel;
  function build() {
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.max(2, Math.round(canvas.clientWidth * dpr));
    canvas.height = Math.max(2, Math.round(canvas.clientHeight * dpr));
    aspect = canvas.width / canvas.height;
    var simH = 176, dyeH = Math.min(800, Math.max(400, canvas.height));
    var simW = Math.max(2, Math.round(simH * aspect)), dyeW = Math.max(2, Math.round(dyeH * aspect));
    freePair(vel); freePair(dye); freePair(pressure); free(div); free(curl);
    vel = pair(simW, simH, gl.RG16F);
    pressure = pair(simW, simH, gl.R16F);
    div = target(simW, simH, gl.R16F);
    curl = target(simW, simH, gl.R16F);
    dye = pair(dyeW, dyeH, gl.RGBA16F, true);
    if (!probe) {
      probe = { tex: gl.createTexture(), fbo: gl.createFramebuffer(), w: PROBE_W, h: PROBE_H };
      gl.bindTexture(gl.TEXTURE_2D, probe.tex);
      gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA8, PROBE_W, PROBE_H);
      gl.bindFramebuffer(gl.FRAMEBUFFER, probe.fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, probe.tex, 0);
    }
    simTexel = [1 / simW, 1 / simH];
    dyeTexel = [1 / dyeW, 1 / dyeH];
  }

  var unit = 0;
  function use(p) { gl.useProgram(p.program); unit = 0; return p.u; }
  function tex(loc, t) { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t.tex); gl.uniform1i(loc, unit++); }
  function draw(to) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, to ? to.fbo : null);
    gl.viewport(0, 0, to ? to.w : canvas.width, to ? to.h : canvas.height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  function add(field, x, y, value, radius) {
    var u = use(P.add);
    tex(u.uTarget, field.read);
    gl.uniform2f(u.uPoint, x, y); gl.uniform4f(u.uValue, value[0], value[1], value[2] || 0, 0);
    gl.uniform1f(u.uAspect, aspect); gl.uniform1f(u.uRadius, radius);
    draw(field.write); field.swap();
  }

  // Which colour comes next: a reshuffled hand of the four, never the same one twice running. Where it lands
  // has nothing to do with which colour it is, so no colour keeps a corner of the screen to itself.
  function halton(i, b) { var f = 1, r = 0; while (i > 0) { f /= b; r += f * (i % b); i = Math.floor(i / b); } return r; }
  var count = 0, hand = [], lastColour = -1, pouring = [];
  function nextColour() {
    if (!hand.length) {
      hand = [0, 1, 2, 3];
      for (var i = 3; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = hand[i]; hand[i] = hand[j]; hand[j] = t; }
      if (hand[3] === lastColour) { hand[3] = hand[0]; hand[0] = lastColour; }
    }
    return (lastColour = hand.pop());
  }
  // Where it lands: of the next few places in an even walk over the water, the one with the least light
  // already there, and never on the line of type.
  function darkPlace() {
    gl.bindTexture(gl.TEXTURE_2D, dye.read.tex);
    gl.generateMipmap(gl.TEXTURE_2D);
    var u = use(P.probe);
    tex(u.uDye, dye.read);
    draw(probe);
    gl.readPixels(0, 0, PROBE_W, PROBE_H, gl.RGBA, gl.UNSIGNED_BYTE, seen);
    var best = null, least = 1e9;
    for (var tries = 0; tries < 9; tries++) {
      count++;
      var x = MARGIN * 0.6 + (1 - MARGIN * 1.2) * halton(count, 2), y = MARGIN * 0.6 + (1 - MARGIN * 1.2) * halton(count, 3);
      var wx = ((x - MARGIN) / (1 - 2 * MARGIN) - lineAt[0]) / (lineHalf[0] + 0.08);
      var wy = ((y - MARGIN) / (1 - 2 * MARGIN) - lineAt[1]) / (lineHalf[1] + 0.2);
      if (wx * wx + wy * wy < 1) continue;
      var cx = Math.min(PROBE_W - 2, Math.max(1, Math.floor(x * PROBE_W))), cy = Math.min(PROBE_H - 2, Math.max(1, Math.floor(y * PROBE_H)));
      var lit = Math.random() * 6;
      for (var dy = -1; dy <= 1; dy++) for (var dx = -1; dx <= 1; dx++) lit += seen[((cy + dy) * PROBE_W + cx + dx) * 4];
      if (lit < least) { least = lit; best = [x, y, wx, wy]; }
    }
    return best || [0.5, 0.12, 0, -1];
  }
  function pour(steps) {
    var at = darkPlace(), k = nextColour(), size = 0.9 + 0.8 * Math.random();
    // it sets off along the edge of the clearing round the type, not into it
    var angle = Math.atan2(at[2], -at[3] * aspect) + (Math.random() < 0.5 ? Math.PI : 0) + (Math.random() - 0.5) * 1.2;
    // the place it is let in moves across the push, like a brush drawn sideways, so the ink goes in as a ribbon
    var across = angle + (Math.random() < 0.5 ? 1 : -1) * (1.2 + 0.7 * Math.random());
    pouring.push({
      x: at[0], y: at[1], dx: Math.cos(angle), dy: Math.sin(angle), ax: Math.cos(across), ay: Math.sin(across),
      size: size, steps: steps, done: 0, reach: (0.14 + 0.16 * Math.random()) / steps,
      light: COLOURS[k].map(function (c) { return c * GAIN[k]; })
    });
  }
  function run() {                          // ink is let in along a short stroke, with a push, so it rolls up into curls
    pouring = pouring.filter(function (p) {
      var ease = Math.sin(Math.PI * (p.done + 0.5) / p.steps);
      var push = 300 * p.size * ease / p.steps;
      add(vel, p.x, p.y, [p.dx * push, p.dy * push], 0.004 * p.size * p.size);
      var rate = ease * ease * 17 / p.steps;   // the push leads and the ink follows, so it arrives as a streak
      add(dye, p.x, p.y, [p.light[0] * rate, p.light[1] * rate, p.light[2] * rate], 0.0009 * p.size * p.size);
      p.x += p.ax * p.reach / aspect; p.y += p.ay * p.reach;
      return ++p.done < p.steps;
    });
  }

  // The water moves in steps of a fixed length, however fast the screen refreshes, so the picture is the same
  // on a fast screen and a slow one.
  var STEP = 1 / 36, time = 0, untilNext = 0;
  function step() {
    var dt = STEP, u, i;
    time += dt;
    u = use(P.stir); tex(u.uVel, vel.read); gl.uniform1f(u.uTime, time); gl.uniform1f(u.uAmp, 0.07 * dt * 60); gl.uniform1f(u.uAspect, aspect);
    draw(vel.write); vel.swap();

    u = use(P.curl); tex(u.uVel, vel.read); gl.uniform2fv(u.uTexel, simTexel); draw(curl);
    u = use(P.eddy); tex(u.uVel, vel.read); tex(u.uF, curl); gl.uniform2fv(u.uTexel, simTexel);
    gl.uniform1f(u.uStrength, 5); gl.uniform1f(u.uDt, dt); draw(vel.write); vel.swap();

    u = use(P.divergence); tex(u.uVel, vel.read); gl.uniform2fv(u.uTexel, simTexel); draw(div);
    for (i = 0; i < 18; i++) {
      u = use(P.pressure); tex(u.uF, pressure.read); tex(u.uDiv, div); gl.uniform2fv(u.uTexel, simTexel);
      draw(pressure.write); pressure.swap();
    }
    u = use(P.project); tex(u.uF, pressure.read); tex(u.uVel, vel.read); gl.uniform2fv(u.uTexel, simTexel);
    draw(vel.write); vel.swap();

    u = use(P.carry); tex(u.uVel, vel.read); tex(u.uSrc, vel.read); gl.uniform2fv(u.uTexel, simTexel);
    gl.uniform1f(u.uDt, dt); gl.uniform1f(u.uKeep, Math.exp(-dt / 3.2)); gl.uniform1f(u.uClear, 0); gl.uniform1f(u.uFade, 0); draw(vel.write); vel.swap();
    u = use(P.carry); tex(u.uVel, vel.read); tex(u.uSrc, dye.read); gl.uniform2fv(u.uTexel, simTexel);
    gl.uniform1f(u.uDt, dt); gl.uniform1f(u.uKeep, Math.exp(-dt / 9)); gl.uniform1f(u.uClear, dt / 0.28); gl.uniform1f(u.uFade, 0.012 * dt);
    gl.uniform2fv(u.uLine, lineAt); gl.uniform2fv(u.uLineHalf, lineHalf); gl.uniform1f(u.uAspect, aspect); gl.uniform1f(u.uMargin, MARGIN);
    draw(dye.write); dye.swap();

    run();
    untilNext -= dt;
    if (untilNext <= 0) { pour(40); untilNext = 1.0 + Math.random() * 0.9; }
  }

  var line = document.querySelector('.prompt'), lineAt = [0.5, 0.5], lineHalf = [0.3, 0.04];
  function findLine() {                     // where the type is, in the picture's own terms
    if (!line) return;
    var c = canvas.getBoundingClientRect(), r = line.getBoundingClientRect();
    if (!c.width || !c.height) return;
    lineAt = [(r.left + r.width / 2 - c.left) / c.width, 1 - (r.top + r.height / 2 - c.top) / c.height];
    lineHalf = [r.width / 2 / c.width, Math.max(r.height, 40) / 2 / c.height];
  }
  function show() {
    gl.bindTexture(gl.TEXTURE_2D, dye.read.tex);
    gl.generateMipmap(gl.TEXTURE_2D);
    var u = use(P.show);
    tex(u.uDye, dye.read);
    gl.uniform2fv(u.uLine, lineAt); gl.uniform2fv(u.uLineHalf, lineHalf);
    gl.uniform1f(u.uMargin, MARGIN); gl.uniform1f(u.uAspect, aspect);
    draw(null);
  }
  function begin() {
    build();
    findLine();
    count = Number(query.get('seed')) || Math.floor(Math.random() * 400);
    hand = []; pouring = []; time = count * 7.3;
    for (var i = 0; i < 5; i++) pour(40);   // some light is already in the water when it is first seen
    var warm = Number(query.get('t')) || 8;
    for (var s = 0; s < warm / STEP; s++) step();
    show();
    root.classList.add('ink-on');
  }

  var owed = 0, last = 0, visible = true, raf = 0;
  function frame(now) {
    raf = 0;
    if (!visible || document.hidden) return;
    owed = Math.min(owed + (now - last) / 1000, 3 * STEP);
    last = now;
    var moved = false;
    while (owed >= STEP) { step(); owed -= STEP; moved = true; }
    if (moved) show();
    raf = requestAnimationFrame(frame);
  }
  function wake() { if (!still && !raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }

  begin();
  wake();
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (e) { visible = e[0].isIntersecting; if (visible) wake(); }).observe(canvas);
  }
  document.addEventListener('visibilitychange', wake);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { findLine(); if (still) show(); });
  var resizing = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizing);
    resizing = setTimeout(function () { begin(); wake(); }, 180);
  });
  // a hand through the water
  var px = null, py = null;
  window.addEventListener('pointermove', function (e) {
    var r = canvas.getBoundingClientRect();
    if (e.clientY > r.bottom || still) { px = null; return; }
    var x = MARGIN + (1 - 2 * MARGIN) * (e.clientX - r.left) / r.width;
    var y = MARGIN + (1 - 2 * MARGIN) * (1 - (e.clientY - r.top) / r.height);
    if (px !== null) add(vel, x, y, [(x - px) * 1100, (y - py) * 1100 / aspect], 0.003);
    px = x; py = y;
  }, { passive: true });
  canvas.addEventListener('webglcontextlost', function (e) { e.preventDefault(); root.classList.add('no-ink'); });
})();
