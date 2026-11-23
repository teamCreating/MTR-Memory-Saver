import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.io.*;
import static org.lwjgl.glfw.GLFW.*;
import static org.lwjgl.opengl.GL11.*;
import org.lwjgl.opengl.GL;
import org.lwjgl.glfw.GLFWErrorCallback;
public final class FramePositiveControl {
 public static void main(String[] args) throws Exception {
  Path output=Path.of(args[0]);long duration=Long.parseLong(args[1]);
  GLFWErrorCallback callback=GLFWErrorCallback.createPrint(System.err);callback.set();
  if(!glfwInit())throw new IllegalStateException("GLFW init failed");
  long window=0;long frames=0;
  try {
   glfwDefaultWindowHints();glfwWindowHint(GLFW_VISIBLE,GLFW_FALSE);glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR,3);glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR,2);glfwWindowHint(GLFW_OPENGL_PROFILE,GLFW_OPENGL_CORE_PROFILE);glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT,GLFW_TRUE);
   window=glfwCreateWindow(640,360,"Memory Saver OpenGL positive control",0,0);if(window==0)throw new IllegalStateException("No GL window");
   glfwMakeContextCurrent(window);GL.createCapabilities();glfwSwapInterval(1);glfwShowWindow(window);
   String context="renderer="+glGetString(GL_RENDERER)+"\nversion="+glGetString(GL_VERSION)+"\nvendor="+glGetString(GL_VENDOR)+"\npid="+ProcessHandle.current().pid()+"\n";
   Files.writeString(output.resolve("ready.txt"),context,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
   long start=System.nanoTime();
   try(BufferedWriter writer=Files.newBufferedWriter(output.resolve("swap-calls.csv"),StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW)) {
    writer.write("Frame,BeforeSwapNanos,AfterSwapNanos\n");
    while(!glfwWindowShouldClose(window)&&System.nanoTime()-start<duration*1000000000L) {
     float phase=(frames%120)/119f;glViewport(0,0,640,360);glClearColor(phase,1f-phase,.25f,1f);glClear(GL_COLOR_BUFFER_BIT);
     if(glGetError()!=GL_NO_ERROR)throw new IllegalStateException("GL error");long before=System.nanoTime();glfwSwapBuffers(window);long after=System.nanoTime();writer.write(frames+","+before+","+after+"\n");writer.flush();glfwPollEvents();frames++;
    }
   }
   Files.writeString(output.resolve("completed.txt"),"swap_calls="+frames+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
  } finally {if(window!=0)glfwDestroyWindow(window);glfwTerminate();callback.free();}
 }
}
